"""Telegram notifications to the owner's phone.

Structured exactly like :mod:`core.sms`, and for the same reason: module
logger, catch everything, log, return a boolean, **never raise**. A Telegram
outage degrades a feature; it must never fail a checkout (§4, §12 risk #17).

Two further rules make that guarantee real:

* **Credentials ship blank** (§17 #93). With no token the module logs one
  warning and sends nothing. Local development and a fresh deploy are
  unaffected, and turning notifications on is a paste into the server ``.env``
  rather than a deploy.
* **Every send fires on** ``transaction.on_commit`` — see :func:`notify`. A
  notification for an order that then rolled back is worse than no
  notification, and a slow HTTP call inside a transaction holds a row lock
  open on the checkout path.

Messages use Telegram's HTML parse mode, so every piece of user-supplied text
goes through :func:`esc` on the way in.
"""
import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils.html import escape

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 10


def esc(value):
    """HTML-escape a value for Telegram's HTML parse mode."""
    return escape('' if value is None else str(value))


def configured():
    """Are both credentials present? Blank is a supported state, not an error."""
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def send(text, *, preview=False):
    """Send one message; return True on success, False on anything else.

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


def notify(text, *, preview=False):
    """Queue a message to go out once the current transaction commits.

    Outside a transaction ``on_commit`` runs the callback immediately, so this
    is safe everywhere and callers never have to know which they are in.
    """
    transaction.on_commit(lambda: send(text, preview=preview))


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


# ------------------------------------------------------------------- events

def notify_new_order(order):
    """A new order, with everything needed to act on it without opening a laptop."""
    lines = [f"🧾 <b>Yangi buyurtma</b> {esc(order.order_no or order.pk)}"]

    items = order.cart.cart_items.select_related('variant__product', 'variant__size')
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

    lines.append(f"\n{esc(order.user.get_full_name() or order.user.username)}"
                 + _phone_line('Telefon', order.phone))
    if order.notes:
        lines.append(f"<b>Izoh:</b> {esc(order.notes)}")

    link = admin_url(order)
    if link:
        lines.append(f'\n<a href="{link}">Buyurtmani ochish</a>')

    notify('\n'.join(lines))


def notify_payment(order):
    """Payment confirmed — short, because the order message already said the rest."""
    notify(f"✅ <b>Toʻlandi</b> {esc(order.order_no or order.pk)}\n"
           f"{esc(order.total_price)} soʻm")


def notify_message(msg):
    """A contact-form message, with the sender's number ready to tap."""
    lines = [
        "✉️ <b>Yangi xabar</b>",
        f"{esc(msg.user.get_full_name() or msg.user.username)} "
        f"(@{esc(msg.user.username)})" + _phone_line('Telefon', msg.phone_num),
        f"\n<b>Mavzu:</b> {esc(msg.topic)}",
        esc(msg.msg_text),
    ]
    link = admin_url(msg)
    if link:
        lines.append(f'\n<a href="{link}">Xabarni ochish</a>')
    notify('\n'.join(lines))


def notify_review(review):
    """A review waiting for moderation. Nothing is public until it is approved."""
    excerpt = (review.text or '')[:200]
    lines = [
        "⭐ <b>Yangi sharh — tasdiqlash kerak</b>",
        f"{esc(review.product.name)} — {'★' * review.rating}",
    ]
    if excerpt:
        lines.append(esc(excerpt))
    if review.images.exists():
        lines.append("📷 Rasm biriktirilgan")
    link = admin_url(review)
    if link:
        lines.append(f'\n<a href="{link}">Sharhni ochish</a>')
    notify('\n'.join(lines))
