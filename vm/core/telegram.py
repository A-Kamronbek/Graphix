"""Telegram notifications to the shop's staff.

Structured exactly like :mod:`core.sms`, and for the same reason: module
logger, catch everything, log, return a boolean, **never raise**. A Telegram
outage degrades a feature; it must never fail a checkout (§4, §12 risk #17).

A notification leaves by one of two routes, chosen by ``.env``:

* **The shop's bot service** (``TELEGRAM_BOT_WEBHOOK_URL``). The bot is a
  program of its own that talks to Telegram; the site POSTs each event to it
  as JSON, with the pre-rendered mesdsage and the facts behind it, and signs
  the request with ``WEBSITE_WEBHOOK_SECRET`` - a value the two sides share
  and nobody else knows (§17 #206). The contract is written down for whoever
  runs the bot in ``docs/integrations/telegram-bot.md``.
* **Straight to the Bot API** (``TELEGRAM_BOT_TOKEN`` and
  ``TELEGRAM_CHAT_ID``), when no bot service is set - the way it worked from
  Phase 6f.

Three rules make the never-raise guarantee real:

* **Credentials ship blank** (§17 #93). With nothing set the module logs one
  warning and sends nothing. Local development and a fresh deploy are
  unaffected, and turning notifications on is a paste into the server ``.env``
  rather than a deploy.
* **Every send fires on** ``transaction.on_commit`` — see :func:`notify`. A
  notification for an order that then rolled back is worse than no
  notification, and a slow HTTP call inside a transaction holds a row lock
  open on the checkout path.
* **The secret never travels unprotected.** The bot service must be HTTPS,
  unless it listens on this same machine; anything else is refused before a
  byte is sent.

Messages use Telegram's HTML parse mode, so every piece of user-supplied text
goes through :func:`esc` on the way in.
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10

#: Where plain HTTP is still acceptable: a bot service on this same machine.
LOOPBACK = {'localhost', '127.0.0.1', '::1'}

#: Sent with every relayed event, so the bot can tell our requests apart and
#: its operator can recognise them in a log.
USER_AGENT = 'GRAPHIX-webhook/1'


def esc(value):
    """HTML-escape a value for Telegram's HTML parse mode."""
    return escape('' if value is None else str(value))


def configured():
    """Are the Bot API credentials present? Blank is a supported state, not an error."""
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def relaying():
    """Is a bot service set? When it is, every notification goes through it."""
    return bool(settings.TELEGRAM_BOT_WEBHOOK_URL)


def send(text, *, preview=False):
    """Send one message straight to the Bot API; True on success, False otherwise.

    Never raises. Callers treat the return value as informational — nothing in
    the project changes behaviour based on whether a notification landed.
    """
    if not configured():
        logger.warning("Telegram is not configured; message not sent")
        return False

    try:
        response = requests.post(
            API.format(token=settings.TELEGRAM_BOT_TOKEN),
            data={
                'chat_id': settings.TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': not preview,
            },
            timeout=TIMEOUT,
        )
        if response.status_code >= 400:
            logger.error("Telegram rejected a message (%s): %s",
                         response.status_code, response.text)
            return False
        return True
    except requests.RequestException as e:
        logger.error("Telegram request error: %s", e)
        return False
    except Exception:
        # Deliberately broad. This runs on the checkout path, and the one thing
        # it must never do is turn a completed order into a 500.
        logger.exception("Telegram send failed unexpectedly")
        return False


def signature(secret, timestamp, body):
    """``sha256=<hex>``: HMAC-SHA256 of ``"<timestamp>.<body>"`` under the secret.

    The timestamp is inside what is signed, so a captured request cannot be
    replayed later with a fresh one; the bot rejects anything too old.
    """
    digest = hmac.new(secret.encode('utf-8'), f'{timestamp}.'.encode('ascii') + body,
                      hashlib.sha256).hexdigest()
    return f'sha256={digest}'


def _safe_url(url):
    """True for an HTTPS URL, or plain HTTP to this machine; False otherwise."""
    parts = urlsplit(url)
    if parts.scheme == 'https' and parts.hostname:
        return True
    return parts.scheme == 'http' and (parts.hostname or '') in LOOPBACK


def relay(event, text, data):
    """POST one event to the shop's bot service; True on a 2xx, False otherwise.

    Never raises. Nothing is sent without the shared secret or to an address
    the secret could be read on the way to, and a redirect is not followed -
    requests would carry our headers, secret included, to wherever it points.
    """
    url = settings.TELEGRAM_BOT_WEBHOOK_URL
    secret = settings.WEBSITE_WEBHOOK_SECRET
    if not secret:
        logger.error("TELEGRAM_BOT_WEBHOOK_URL is set but WEBSITE_WEBHOOK_SECRET "
                     "is blank; %s not sent", event)
        return False
    if not _safe_url(url):
        logger.error("The Telegram bot service must be https:// (or http:// on "
                     "this machine); %s not sent", event)
        return False

    try:
        body = json.dumps({
            'event': event,
            'sent_at': timezone.localtime(),
            'text': text,
            'parse_mode': 'HTML',
            'data': data,
        }, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        timestamp = str(int(time.time()))
        response = requests.post(
            url,
            data=body,
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'User-Agent': USER_AGENT,
                'X-Webhook-Event': event,
                'X-Webhook-Timestamp': timestamp,
                'X-Webhook-Signature': signature(secret, timestamp, body),
                'X-Webhook-Secret': secret,
            },
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        if not 200 <= response.status_code < 300:
            logger.error("The Telegram bot service refused %s (%s): %s",
                         event, response.status_code, response.text[:300])
            return False
        return True
    except requests.RequestException as e:
        logger.error("Telegram bot service request error (%s): %s", event, e)
        return False
    except Exception:
        # The same reasoning as in send(): this must never become a 500.
        logger.exception("Relaying %s to the Telegram bot service failed unexpectedly", event)
        return False


def deliver(event, text, data=None, *, preview=False):
    """Send one notification by whichever route ``.env`` sets up."""
    if relaying():
        return relay(event, text, data or {})
    return send(text, preview=preview)


def notify(text, *, event='notification', data=None, preview=False):
    """Queue a notification to go out once the current transaction commits.

    Outside a transaction ``on_commit`` runs the callback immediately, so this
    is safe everywhere and callers never have to know which they are in.
    """
    transaction.on_commit(lambda: deliver(event, text, data, preview=preview))


# ------------------------------------------------------------------ helpers

def admin_url(obj):
    """Absolute link to an object's Django admin page, for the owner's phone."""
    from django.urls import NoReverseMatch, reverse
    try:
        path = reverse(
            f'admin:{obj._meta.app_label}_{obj._meta.model_name}_change',
            args=[obj.pk],
        )
    except NoReverseMatch:
        return ''
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def _phone_line(label, phone):
    """A tap-to-call line. The owner rings the customer from the notification."""
    if not phone:
        return ''
    return f"\n{esc(label)}: <a href=\"tel:{esc(phone)}\">{esc(phone)}</a>"


def _som(amount):
    """A so'm amount as a whole number - the columns carry no fractions."""
    return None if amount is None else int(amount)


# ------------------------------------------------------------------- events

def notify_new_order(order):
    """A new order, with everything needed to act on it without opening a laptop."""
    lines = [f"🧾 <b>Yangi buyurtma</b> {esc(order.order_no or order.pk)}"]

    items = list(order.cart.cart_items.select_related('variant__product', 'variant__size'))
    for item in items:
        lines.append(f"• {esc(item.variant.product.name)} — "
                     f"{esc(item.variant.size.size)} × {item.quantity}")

    lines.append(f"\n<b>Jami:</b> {esc(order.total_price)} soʻm")
    if order.delivery_option_id:
        lines.append(f"<b>Yetkazish:</b> {esc(order.delivery_option.name)} — "
                     f"{esc(order.delivery_price)} soʻm")
    # The frozen text, not the live rows: it is what the customer actually chose.
    if order.location_snapshot:
        lines.append(f"<b>Manzil:</b> {esc(order.location_snapshot)}")
    if order.latitude is not None and order.longitude is not None:
        maps = (f"https://www.google.com/maps/search/?api=1"
                f"&query={order.latitude},{order.longitude}")
        lines.append(f'<a href="{maps}">Xaritada koʻrish</a>')
    lines.append(f"<b>Toʻlov:</b> {esc(order.get_payment_method_display())}")

    # The name on the parcel, which is not always the account's.
    who = order.recipient_name or order.user.get_full_name() or order.user.username
    lines.append(f"\n{esc(who)}"
                 + _phone_line('Telefon', order.phone))
    if order.notes:
        lines.append(f"<b>Izoh:</b> {esc(order.notes)}")

    link = admin_url(order)
    if link:
        lines.append(f'\n<a href="{link}">Buyurtmani ochish</a>')

    # The same facts, unformatted, for a bot that lays the message out itself.
    # Nothing here that the message above does not already say (§17 #206).
    delivery = order.delivery_option if order.delivery_option_id else None
    has_pin = order.latitude is not None and order.longitude is not None
    data = {'order': {
        'id': order.pk,
        'number': order.order_no or str(order.pk),
        'status': order.status,
        'created_at': order.created_at,
        'total': _som(order.total_price),
        'currency': 'UZS',
        'payment_method': order.payment_method,
        'delivery': {
            'code': delivery.code,
            'name': delivery.name,
            'price': _som(order.delivery_price),
            'to_branch': delivery.requires_branch,
        } if delivery else None,
        'address': order.location_snapshot,
        'location': {'lat': float(order.latitude),
                     'lng': float(order.longitude)} if has_pin else None,
        'recipient': {'name': who, 'phone': order.phone},
        'notes': order.notes,
        'items': [{'product': item.variant.product.name,
                   'size': item.variant.size.size,
                   'quantity': item.quantity,
                   'price': _som(item.price_stat)} for item in items],
        'admin_url': link,
    }}
    notify('\n'.join(lines), event='order.created', data=data)


def notify_payment(order):
    """Payment confirmed — short, because the order message already said the rest."""
    notify(f"✅ <b>Toʻlandi</b> {esc(order.order_no or order.pk)}\n"
           f"{esc(order.total_price)} soʻm",
           event='order.paid',
           data={'order': {
               'id': order.pk,
               'number': order.order_no or str(order.pk),
               'total': _som(order.total_price),
               'currency': 'UZS',
               'admin_url': admin_url(order),
           }})


def notify_message(msg):
    """A contact-form message, with the sender's number ready to tap."""
    name = msg.user.get_full_name() or msg.user.username
    lines = [
        "✉️ <b>Yangi xabar</b>",
        f"{esc(name)} "
        f"(@{esc(msg.user.username)})" + _phone_line('Telefon', msg.phone_num),
        f"\n<b>Mavzu:</b> {esc(msg.topic)}",
        esc(msg.msg_text),
    ]
    link = admin_url(msg)
    if link:
        lines.append(f'\n<a href="{link}">Xabarni ochish</a>')
    notify('\n'.join(lines), event='message.created', data={'message': {
        'id': msg.pk,
        'name': name,
        'username': msg.user.username,
        'phone': msg.phone_num,
        'subject': msg.topic,
        'text': msg.msg_text,
        'admin_url': link,
    }})


def notify_review(review):
    """A review waiting for moderation. Nothing is public until it is approved."""
    excerpt = (review.text or '')[:200]
    photos = review.images.exists()
    lines = [
        "⭐ <b>Yangi sharh — tasdiqlash kerak</b>",
        f"{esc(review.product.name)} — {'★' * review.rating}",
    ]
    if excerpt:
        lines.append(esc(excerpt))
    if photos:
        lines.append("📷 Rasm biriktirilgan")
    link = admin_url(review)
    if link:
        lines.append(f'\n<a href="{link}">Sharhni ochish</a>')
    notify('\n'.join(lines), event='review.created', data={'review': {
        'id': review.pk,
        'product': review.product.name,
        'rating': review.rating,
        'text': review.text or '',
        'has_photos': photos,
        'admin_url': link,
    }})
