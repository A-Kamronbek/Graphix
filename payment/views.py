"""Checkout, Click payment start/webhook, and order views."""
import functools
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.decorators import classonlymethod
from django.views.decorators.http import require_POST
from django.utils import translation
from django.utils.translation import gettext as _, gettext_lazy, ngettext
# `...django.views`, not `...django.webhooks`. The two modules hold the
# same handlers; only these are wrapped in `csrf_exempt`, and a payment
# gateway has no CSRF token to send (§17 #270).
from tolov.core.exceptions import AccountNotFound, PermissionDenied
from tolov.integrations.django.models import PaymentTransaction
from tolov.integrations.django.views import (BaseClickWebhookView,
                                             BaseOctoWebhookView,
                                             BasePaymeWebhookView)

from core.i18n import tfield
from core.ratelimit import (RATE_LIMIT_MESSAGE, is_currently_limited,
                            is_rate_limited)
from product.templatetags.price_format import price
from .models import (SOLD, DeliveryOption, District, Order, PaymentOption, Region,
                     RECIPIENT_NAME_MAX)
from user.models import normalize_uz_phone, phone_regex
from . import promos, services

logger = logging.getLogger(__name__)


# ---------- presentation helper ----------

def _annotate_lines(items):
    """Attach a ``line_total`` (price_stat * quantity) to each line for templates."""
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out

# ---------- checkout: cart → order ----------

def _delivery_context():
    """Everything the checkout form needs to render its two branches.

    Districts are grouped by region here rather than fetched per region by the
    browser: there are only 221 of them, the whole set is a few kilobytes of
    JSON, and shipping it with the page means the district drawer opens
    instantly and still works with the network gone. It also keeps the checkout
    free of an endpoint that could fail mid-order.
    """
    # Only what Uzpost can be sent to: its regions and districts, each with
    # Uzpost's id (§17 #378). A row switched on by hand without one would only
    # be refused by `Order.clean` after the customer had chosen it.
    regions = list(Region.objects.filter(is_active=True, uzpost_id__isnull=False))
    districts = (District.objects.filter(is_active=True, uzpost_id__isnull=False,
                                         region__is_active=True)
                 .select_related('region'))

    by_region = {r.pk: {'district': [], 'city': [], 'other': []} for r in regions}
    for d in districts:
        bucket = by_region.get(d.region_id)
        if bucket is not None:
            bucket[d.kind].append({
                'id': d.pk,
                'name': tfield(d, 'name'),
                # All three spellings travel with the row so the map can match
                # whatever Google calls the place against any of them (§17 #116).
                # Google's Uzbek for Chilonzor is "Chilanzar" in English and
                # "Чиланзар" in Russian; one column would match one of those.
                'match': [n for n in (d.name, d.name_ru, d.name_en) if n],
                # The district's pin on the office map: its centre as Uzpost
                # gives it (§17 #381). Absent when the row has none.
                'lat': float(d.latitude) if d.latitude is not None else None,
                'lng': float(d.longitude) if d.longitude is not None else None,
            })

    return {
        'delivery_options': list(DeliveryOption.objects.filter(is_active=True)),
        'payment_options': list(PaymentOption.objects.filter(is_active=True)),
        'regions': regions,
        # Keyed by region id, split by kind, so the drawer can put Tumanlar and
        # Shaharlar under their own headings (§17 #87).
        'districts_json': json.dumps(by_region, ensure_ascii=False),
        # The same rows unserialised, for the options the select ships with.
        'districts_by_region': by_region,
        'google_maps_key': settings.GOOGLE_MAPS_API_KEY,
        # The provider's own URL, built here rather than written into the
        # template: the key, the page's language and the region all live on
        # this side, and since §18 #34 the page holds the address instead of
        # fetching it - the script is loaded when the customer asks for a map.
        'google_maps_src': _maps_src(),
    }


def _maps_src():
    """The Google Maps loader URL, or '' when no key is configured.

    ``language`` and ``region`` are what make the place names Google returns
    comparable to ours: asked in the page's own language, and biased to
    Uzbekistan so a lookup never drifts to a same-named place abroad.
    """
    key = settings.GOOGLE_MAPS_API_KEY
    if not key:
        return ''
    return ('https://maps.googleapis.com/maps/api/js'
            '?key=%s&loading=async&language=%s&region=UZ&callback=GXMapReady'
            % (quote(key, safe=''), translation.get_language() or 'uz'))


def _district_options(regions, by_region, region_pk):
    """The district select's options as the page ships them: ``[(heading, rows)]``.

    The script fills this select from the JSON beside it, and for a long time
    that was the only thing that did: with scripts off the select held one
    placeholder, no district could be chosen, and no order could be placed.
    It also meant a form sent back with a mistake came back without its
    district, scripts or not.

    With a region chosen, its own districts are listed under the headings the
    drawer uses. With none, every district is listed under its region, so a
    customer without scripts picks from one list. The server checks that the
    two agree either way.
    """
    if region_pk in by_region:
        chosen = by_region[region_pk]
        headings = (('district', _('Tumanlar')), ('city', _('Shaharlar')), ('other', ''))
        return [(heading, chosen[kind]) for kind, heading in headings if chosen[kind]]
    return [(tfield(region, 'name'),
             by_region[region.pk]['district'] + by_region[region.pk]['city']
             + by_region[region.pk]['other'])
            for region in regions]


def _read_delivery(post):
    """Pull the delivery fields out of a POST. Returns (kwargs, option).

    Region and district are read for **both** methods (§17 #106) — the courier
    needs them as much as the post office does, and since Phase 22 an office
    order is addressed by its district alone and nothing else is read for it
    (§17 #377). A home order adds the street and, from the map, the pin. That
    is what stops a stale value from the hidden half of the form reaching the
    database and quietly contradicting the rest of the order.
    """
    option = DeliveryOption.objects.filter(
        code=post.get('delivery_option', '').strip(), is_active=True
    ).first()

    kwargs = {
        'delivery_option': option,
        'region': None, 'district': None, 'postal_index': '',
        'location_note': '', 'address': '', 'address_source': '',
        'latitude': None, 'longitude': None,
    }
    if option is None:
        return kwargs, None

    kwargs['region'] = Region.objects.filter(pk=_int(post.get('region')),
                                             is_active=True).first()
    kwargs['district'] = District.objects.filter(pk=_int(post.get('district')),
                                                 is_active=True).first()
    # Only meaningful for the Boshqa escape; ignored otherwise, so a stray
    # value cannot end up on a perfectly ordinary order.
    if kwargs['district'] is not None and kwargs['district'].kind == District.Kind.OTHER:
        kwargs['location_note'] = post.get('location_note', '').strip()[:160]

    if not option.requires_branch:
        kwargs['address'] = post.get('address', '').strip()
        source = post.get('address_source', '').strip()
        kwargs['address_source'] = source if source in ('map', 'manual') else 'manual'
        if kwargs['address_source'] == 'map':
            kwargs['latitude'] = _decimal(post.get('latitude'))
            kwargs['longitude'] = _decimal(post.get('longitude'))
            # A pin that did not survive the round trip is not a map order: the
            # address is what the courier follows either way (§17 #91).
            if kwargs['latitude'] is None or kwargs['longitude'] is None:
                kwargs['address_source'] = 'manual'

    return kwargs, option


def _int(raw):
    """Parse an id from a form field, or None."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _decimal(raw):
    """Parse a coordinate, or None. A malformed one is absent, never zero."""
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError, TypeError):
        return None
    # Uzbekistan's bounding box, roughly — the same check the branch loader used
    # to make, and it still catches the one typo that produces a perfect-looking
    # coordinate pointing at another country.
    return value if -180 <= value <= 180 else None


def _refuse_off_sale(request, lines):
    """Send the customer back to the cart, naming what can no longer be bought.

    Named by product, once each: two sizes of one withdrawn design are one
    thing to remove as far as the customer is concerned. The cart marks the
    same lines, so the message and the page point at the same rows (§17 #294).
    """
    names = list(dict.fromkeys(tfield(line.variant.product, 'name') for line in lines))
    messages.error(request, ngettext(
        "%(names)s endi sotuvda yoʻq. Buyurtma berish uchun uni savatdan olib tashlang.",
        "%(names)s endi sotuvda yoʻq. Buyurtma berish uchun ularni savatdan olib tashlang.",
        len(names)) % {'names': ', '.join(names)})
    return redirect('cart')


# ---------- the promo code ----------

#: How many wrong promo codes are answered in ten minutes: from one customer,
#: and from one address. A code is short and worth money, so the form that
#: says whether one is good cannot be asked without end (§17 #134).
#:
#: A refusal is counted and an accepted code is not. The form is posted once
#: to apply a code, again to place the order, and once more for every field
#: the customer has to correct, and none of those is a guess. A whole
#: campaign's customers can also sit behind one mobile carrier's address,
#: each typing a good code once.
PROMO_TRIES = 10
PROMO_TRIES_ADDRESS = 30

#: How much of what was typed into the field is read. A code is at most 24
#: characters; the rest is room for stray spaces, and anything past it is
#: not a code.
PROMO_TYPED_MAX = 40

#: What the page says under the field once a code is in: what it takes off
#: and what is left to pay. Written with braces and not gettext's own
#: placeholders because the same two sentences are handed to `checkout.js`,
#: which fills them in again when the delivery method changes.
PROMO_SAID = gettext_lazy("Chegirma: {discount} soʻm. Jami: {total} soʻm.")
PROMO_SAID_PRODUCT = gettext_lazy(
    "Chegirma ({product}): {discount} soʻm. Jami: {total} soʻm.")


def _fees(options, item_count):
    """What each delivery method on offer costs this cart, by the method's code."""
    return {option.code: Decimal(option.price_for_items(item_count)) for option in options}


def _promo_idents(request):
    """The two counters a guess is kept under: ``(scope, limit, ident)`` each."""
    return (('promo_customer', PROMO_TRIES, 'u%s' % request.user.pk),
            ('promo_address', PROMO_TRIES_ADDRESS, None))


def _promo_blocked(request):
    """Whether this customer or this address has had its wrong codes. Counts nothing."""
    return any(is_currently_limited(request, scope, limit, ident=ident)
               for scope, limit, ident in _promo_idents(request))


def _count_refusal(request):
    """One wrong code, against the customer and against the address."""
    for scope, limit, ident in _promo_idents(request):
        is_rate_limited(request, scope, limit, 600, ident=ident)


def _try_promo(request, typed, items, fees):
    """The typed code against this cart: ``(preview, '')`` or ``(None, why)``.

    Asked first whether either counter is already full, without moving them.
    A customer who has been stopped adds nothing more to the address's count,
    so one account cannot use up the address for everybody behind it.

    Every refusal is a guess, not only "no such code": being told a code is
    not for this cart, or is below its minimum, is how a guesser learns the
    code is real.
    """
    if _promo_blocked(request):
        return None, RATE_LIMIT_MESSAGE
    try:
        return promos.preview(typed, request.user, items, fees), ''
    except promos.Refused as refusal:
        _count_refusal(request)
        return None, refusal.message


def _promo_said(preview, discount, total):
    """The sentence under the field for a code that is in, or '' for none."""
    if preview is None or not discount:
        return ''
    if preview.product is not None:
        return PROMO_SAID_PRODUCT.format(product=tfield(preview.product, 'name'),
                                         discount=price(discount), total=price(total))
    return PROMO_SAID.format(discount=price(discount), total=price(total))


def _promo_payload(preview):
    """A previewed code as the page's script reads it."""
    return {
        'code': preview.promo.code,
        'discounts': {method: int(off) for method, off in preview.discounts.items()},
        'product': tfield(preview.product, 'name') if preview.product is not None else '',
    }


@login_required
def checkout(request):
    """Collect delivery details, validate them, and turn the cart into an Order.

    The delivery step is one choice that reveals one of two different forms, and
    nothing from the branch the customer did not pick is submitted, validated or
    stored (§9 Phase 6d). Validation goes through ``Order.clean`` rather than
    being written again here, so the view and the model cannot drift apart about
    what a valid order is.
    """
    cart = services.get_open_cart(request.user)
    if not cart or not cart.cart_items.exists():
        placed = _just_placed(request)
        if placed:
            # Back from Telegram or a gateway's page: the order, not an
            # empty basket (§17 #409).
            return redirect('order_detail', pk=placed)
        messages.error(request, _("Savat boʻsh."))
        return redirect('cart')

    items_qs = (
        cart.cart_items
        .select_related('variant__product', 'variant__size', 'variant__colour')
        .prefetch_related('variant__product__images')
    )
    items = _annotate_lines(items_qs)
    # Before the form rather than after it: a customer should not fill in an
    # address for a cart that cannot be ordered.
    off_sale = [it for it in items if not it.variant.is_on_sale]
    if off_sale:
        return _refuse_off_sale(request, off_sale)
    subtotal = sum((it.line_total for it in items), Decimal('0'))
    item_count = sum(it.quantity for it in items)

    context = {'items': items, 'subtotal': subtotal, 'item_count': item_count,
               'recipient_name_max': RECIPIENT_NAME_MAX,
               'promo_said_template': PROMO_SAID,
               'promo_said_product_template': PROMO_SAID_PRODUCT,
               'promo_nothing': promos.MESSAGES[promos.NOTHING_OFF]}
    context.update(_delivery_context())
    fees = _fees(context['delivery_options'], item_count)
    # What each method costs this cart, which is not always its list price: a
    # tier can be free from so many items. The script's totals read this.
    for option in context['delivery_options']:
        option.fee = fees[option.code]
    # The promo code in play, if any, and why one was refused. Held here so
    # that every way back to the form below shows the same thing.
    code = {'preview': None, 'error': ''}

    def again(form_data, delivery=Decimal('0')):
        """Re-render the form with what the customer typed still in it."""
        preview = code['preview']
        discount = (preview.discounts.get(form_data.get('delivery_option'), Decimal('0'))
                    if preview else Decimal('0'))
        total = subtotal + delivery - discount
        if preview and not discount and not code['error']:
            # Good for this cart, and nothing off the delivery method chosen:
            # free delivery where delivery is already free. The script says
            # the same when the method is changed.
            code['error'] = promos.MESSAGES[promos.NOTHING_OFF]
        context.update({
            'delivery': delivery, 'discount': discount, 'total': total,
            'form_data': form_data,
            'district_options': _district_options(
                context['regions'], context['districts_by_region'],
                form_data.get('region')),
            'promo': preview,
            'promo_error': code['error'],
            'promo_said': _promo_said(preview, discount, total),
            # For the script, which shows the figure for whichever delivery
            # method is picked. The server works the real one out under the
            # lock; this is the preview (§17 #310).
            'promo_json': json.dumps(_promo_payload(preview), ensure_ascii=False)
            if preview else '',
        })
        return render(request, 'payment/checkout.html', context)

    if request.method != 'POST':
        default = next((o for o in context['delivery_options']), None)
        delivery = Decimal(default.price_for_items(item_count)) if default else Decimal('0')
        # The account's own name and number to start from, both editable: a
        # parcel is often for someone else. Every customer has a number, since
        # the checkout needs a sign-in. A name they never gave stays blank -
        # never "Xaridor", and never the username, which is the number again
        # (§17 #374).
        return again({'delivery_option': default.code if default else '',
                      'name': request.user.get_full_name(),
                      'phone': request.user.phone}, delivery)

    post = request.POST
    name = post.get('name', '').strip()
    # The field shows +998 and takes the nine digits after it; a number typed
    # or pasted whole comes too. Both are brought to the one form every number
    # is kept in, so the order and the field shown again agree.
    phone = normalize_uz_phone(post.get('phone', '').strip())
    notes = post.get('notes', '').strip()

    delivery_kwargs, option = _read_delivery(post)
    delivery = Decimal(option.price_for_items(item_count)) if option else Decimal('0')

    # What the customer typed is what gets re-rendered on an error, even when
    # the order itself would not keep it — losing a half-typed address because
    # the delivery method was wrong is its own small insult.
    form_data = {
        'name': name, 'phone': phone, 'notes': notes,
        'address': post.get('address', '').strip(),
        'payment_method': post.get('payment_method', '').strip(),
        'delivery_option': option.code if option else '',
        'region': delivery_kwargs['region'].pk if delivery_kwargs['region'] else '',
        'district': delivery_kwargs['district'].pk if delivery_kwargs['district'] else '',
        'location_note': delivery_kwargs['location_note'],
        'address_source': delivery_kwargs['address_source'],
        'latitude': delivery_kwargs['latitude'],
        'longitude': delivery_kwargs['longitude'],
        # As typed, so a refused code comes back to be corrected (§17 #133).
        'promo_code': post.get('promo_code', '').strip()[:PROMO_TYPED_MAX],
    }

    # The code first, before anything else on the form is judged: "Qoʻllash"
    # is pressed by a customer who has not finished the address yet, and they
    # are owed an answer about the code and not a list of empty fields.
    if 'remove_promo' in post:
        form_data['promo_code'] = ''
        return again(form_data, delivery)
    if form_data['promo_code']:
        code['preview'], code['error'] = _try_promo(
            request, form_data['promo_code'], items, fees)
    elif 'apply_promo' in post:
        code['error'] = _("Promokodni kiriting.")
    if code['error'] or 'apply_promo' in post:
        # A refused code stops the order as well as the preview. The customer
        # typed it expecting to pay less, and an order placed at the full
        # price would be a surprise at the gateway.
        if code['error']:
            messages.error(request, code['error'])
        return again(form_data, delivery)

    # The payment method has to be an option the shop currently offers. Anything
    # else is refused rather than defaulted past: cash is switched off, and a
    # POSTed `cash` must not quietly become a Click order the customer never
    # agreed to (§17 #94, amended — the method stays, it is just inactive).
    active_codes = {o.code for o in context['payment_options']}
    payment_method = form_data['payment_method']
    if payment_method not in active_codes or payment_method not in Order.PaymentMethod.values:
        messages.error(request, _("Toʻlov usulini tanlang."))
        return again(form_data, delivery)

    if option is None:
        messages.error(request, _("Yetkazib berish turini tanlang."))
        return again(form_data, delivery)

    if not name or not phone:
        messages.error(request, _("Ism va telefon raqamni toʻldiring."))
        return again(form_data, delivery)

    # The column's own limit, said as a sentence - not a 500, and not a name
    # quietly shortened on the way to the parcel (§17 #131, #154).
    if len(name) > RECIPIENT_NAME_MAX:
        messages.error(request, _("Ism %(n)d belgidan oshmasligi kerak.")
                       % {'n': RECIPIENT_NAME_MAX})
        return again(form_data, delivery)

    # Digits from another script read as digits to the pattern, and the
    # courier cannot dial them: refused as the sign-in form refuses them.
    try:
        if any(ch.isdigit() and not ch.isascii() for ch in phone):
            raise ValidationError(phone_regex.message)
        phone_regex(phone)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return again(form_data, delivery)

    # One validator for both paths. Building an unsaved Order and asking it is
    # cheaper than repeating the rules, and it guarantees the view and
    # Order.clean can never disagree about what a valid order is.
    probe = Order(**delivery_kwargs)
    try:
        probe.clean()
    except ValidationError as e:
        for message in e.messages:
            messages.error(request, message)
        return again(form_data, delivery)

    try:
        order = services.create_order_from_cart(
            request.user, cart,
            phone=phone, notes=notes, recipient_name=name,
            payment_method=payment_method, delivery=delivery,
            promo=code['preview'].promo if code['preview'] else None,
            **delivery_kwargs,
        )
    except promos.Refused as refusal:
        # Good at the form a moment ago and not under the lock: switched off,
        # used up, or the cart changed in another tab. Nothing was written.
        code['preview'], code['error'] = None, refusal.message
        messages.error(request, refusal.message)
        return again(form_data, delivery)
    except services.CartAlreadyCheckedOut as e:
        messages.info(request, _("Buyurtma allaqachon rasmiylashtirilgan."))
        return redirect('order_detail', pk=e.existing_order.id)
    except services.EmptyCart:
        messages.error(request, _("Savat boʻsh."))
        return redirect('cart')
    except services.OffSaleItems as e:
        return _refuse_off_sale(request, e.lines)

    # Said on the order's page, where a Telegram order lands. Not before a
    # gateway's page: it would be waiting on the order's page when the
    # customer came back from paying.
    if order.payment_method not in services.GATEWAY_CREDENTIALS:
        messages.success(request, _("Buyurtma qabul qilindi. Toʻlovni amalga oshiring."))
    request.session[PLACED_KEY] = order.id
    return _pay(request, order)


@login_required
@require_POST
def checkout_promo(request):
    """What a typed promo code takes off this cart, for the checkout's script.

    The page works without this: "Qoʻllash" is a real button that posts the
    form, and the checkout comes back with the discount in it. This is the
    same answer as JSON, so that with scripts running the summary changes in
    place and nothing the customer has typed is sent anywhere yet.

    Tries are counted here exactly as they are on the form.
    """
    cart = services.get_open_cart(request.user)
    items = (list(cart.cart_items.select_related('variant__product'))
             if cart else [])
    if not items:
        return JsonResponse({'ok': False, 'error': _("Savat boʻsh.")})
    typed = request.POST.get('promo_code', '').strip()[:PROMO_TYPED_MAX]
    if not typed:
        return JsonResponse({'ok': False, 'error': _("Promokodni kiriting.")})
    fees = _fees(DeliveryOption.objects.filter(is_active=True),
                 sum(it.quantity for it in items))
    preview, error = _try_promo(request, typed, items, fees)
    if preview is None:
        return JsonResponse({'ok': False, 'error': str(error)})
    return JsonResponse({'ok': True, **_promo_payload(preview)})


# ---------- payment ----------

#: The session key that tells an order's page to open the Telegram chat at
#: once: set by the checkout, read once by the page (§17 #405).
OPEN_CHAT_KEY = 'gx_open_chat'

#: The session key holding the order the checkout last placed (§17 #409).
PLACED_KEY = 'gx_placed'


def _just_placed(request):
    """The order this session's checkout placed, while it waits for payment.

    Back from Telegram or from a gateway's page is the checkout, and not the
    order's page: browsers skip, on Back, a page that went on by itself
    without being tapped, as the order's page does when it opens the chat.
    The checkout, its basket empty now, sends the customer to that order
    instead of saying the basket is empty. Only while the order waits: once
    it is paid or cancelled the basket is simply empty again (§17 #409).
    """
    pk = request.session.get(PLACED_KEY)
    if pk and Order.objects.filter(pk=pk, user=request.user,
                                   status=Order.Status.PAYING).exists():
        return pk
    request.session.pop(PLACED_KEY, None)
    return None


def _pay(request, order):
    """Send the customer on to pay for ``order``, with no page in between.

    A gateway's order goes straight to the gateway's own page, which comes
    back to the order's details. A Telegram order goes to its details page,
    which opens the chat with the shop's admin at once (§17 #405). Back from
    either is the checkout, which sends the customer on to the order
    (`_just_placed`, §17 #409).

    When a gateway cannot make a link the order exists already, so the
    customer lands on its page, told why, with the button there to try again
    (§9 Phase 23 item 38). Which gateway builds the link is
    `services.generate_paylink`'s business, not this view's.
    """
    if order.payment_method not in services.GATEWAY_CREDENTIALS:
        if order.payment_method == Order.PaymentMethod.TELEGRAM:
            request.session[OPEN_CHAT_KEY] = order.id
        return redirect('order_detail', pk=order.id)

    return_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
    try:
        return redirect(services.generate_paylink(order, return_url))
    except services.PaymentMethodUnavailable:
        # A method whose credentials are blank cannot make a link. Told
        # plainly rather than sent at a gateway that will show a broken page.
        messages.info(request, _("Bu toʻlov usuli uchun onlayn toʻlov yoʻq."))
    except services.PaymentGatewayError:
        # Reachable and said no, or not reachable at all. A different message
        # from the one above on purpose: this order is still PAYING and the
        # method will probably work in an hour, so telling the customer it has
        # no online payment would send them away from one that does.
        messages.error(request, _("Toʻlov tizimi hozir javob bermayapti. "
                                  "Iltimos, birozdan soʻng qayta urinib "
                                  "koʻring."))
    return redirect('order_detail', pk=order.id)


def _pay_context(request, order):
    """What an order's pay button needs, or None when there is nothing to pay.

    ``kind`` is 'gateway' for a form posting to `payment_start`, 'telegram'
    for the link that opens the chat, with ``open`` true the one time the
    checkout has just sent the customer here. Cash, switched off, has no
    online step and so no button.
    """
    if order.status != Order.Status.PAYING:
        return None
    if order.payment_method in services.GATEWAY_CREDENTIALS:
        return {'kind': 'gateway'}
    if order.payment_method == Order.PaymentMethod.TELEGRAM:
        return {'kind': 'telegram',
                'link': services.telegram_pay_link(order),
                'admin': services.telegram_admin(),
                'open': request.session.pop(OPEN_CHAT_KEY, None) == order.id}
    return None


def payment(request, order_id):
    """Where the payment page was: the order's details page now (§17 #405).

    The URL name keeps resolving (§4.2) so a link made before still lands;
    the order's page checks that the order is the customer's.
    """
    return redirect('order_detail', pk=order_id)


@login_required
@require_POST
def payment_start(request, order_id):
    """The order page's pay button: send this order on to be paid.

    Only while the order is still PAYING.
    """
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.status != Order.Status.PAYING:
        messages.info(request, _("Bu buyurtma uchun toʻlov holati "
                                 "allaqachon oʻzgargan."))
        return redirect('order_status', pk=order.id)
    return _pay(request, order)


class PaidByWebhook:
    """What every gateway's callback does with a successful payment.

    A mixin rather than three copies, because the three hooks differ only in
    which base class they sit on. tolov hands each one its own
    `PaymentTransaction`, whose ``account_id`` is the id we passed when the
    pay link was made — so resolving the order is one lookup, and
    `apply_successful_payment` stays the only place an order's status moves,
    knowing nothing about which gateway called it (§17 #253).
    """

    def successfully_payment(self, params, transaction):
        order = self._order(transaction)
        if order is not None:
            services.apply_successful_payment(order)

    def cancelled_payment(self, params, transaction):
        order = self._order(transaction)
        if order is not None:
            services.apply_cancelled_payment(order)

    @classonlymethod
    def as_view(cls, **initkwargs):
        """Answer, rather than raise, when this gateway has no credentials.

        tolov checks its settings in the view's ``__init__``, and Django calls
        that per request inside the closure ``as_view`` returns. So a gateway
        that is switched off and unconfigured does not fail at startup where
        somebody would notice: it raises on the callback, Django answers 500,
        and the gateway reads 500 as "try again" and retries for ever. §4 says
        an external integration degrades a feature and never 500s a page, and
        this is the callback half of that rule.

        It is the construction that is guarded and nothing else. An exception
        raised while a callback is genuinely being handled still propagates,
        because that is a real defect, and turning it into a quiet 503 could
        hide a payment that was taken and never written down.

        The wrapper keeps the view's own attributes - ``csrf_exempt`` among
        them, which a test reads directly (§17 #270).
        """
        view = super().as_view(**initkwargs)

        @functools.wraps(view)
        def guarded(request, *args, **kwargs):
            try:
                cls(**initkwargs)
            except Exception as exc:
                # The method check comes off the class, so a GET still gets the
                # 405 it would get from a configured view. That answer is what
                # says the route still resolves - the smoke matrix asserts it
                # and the uptime monitor watches it, because a 404 there means
                # the webhook has moved and payments are failing in silence.
                allowed = [m.upper() for m in cls.http_method_names
                           if hasattr(cls, m)]
                if request.method not in allowed:
                    return HttpResponseNotAllowed(allowed)
                logger.error(
                    '%s callback refused: this gateway is not configured on '
                    'this installation (%s: %s)',
                    cls.__name__, type(exc).__name__, exc)
                return HttpResponse(status=503)
            return view(request, *args, **kwargs)

        return guarded

    @staticmethod
    def refuse_cancelled(order):
        """Tell a gateway that asks before it charges: a cancelled order is not there.

        A cancelled order could still be paid for through a pay page opened
        before it was cancelled. That mattered little until promo codes:
        cancelling an order frees its code, so a once-per-customer code could
        be put on order after order, each cancelled in turn, and all of them
        paid for afterwards at the discount.

        Only where the gateway is asking. Once it has charged the card the
        payment is honoured whatever the order reads, because the money is
        real: ``apply_successful_payment`` still makes a cancelled order paid.
        """
        if order.status == Order.Status.CANCELLED:
            raise AccountNotFound('Order %s was cancelled' % order.pk)

    @classmethod
    def _order(cls, transaction):
        """The order this transaction is for, or None with a line in the log.

        A callback naming an order that is not there is not an exception worth
        raising: the gateway would see a 500 and retry it forever. It is
        logged and answered, which is what every other external call on this
        site does (§4, the `core/sms.py` pattern).
        """
        order = Order.objects.filter(pk=transaction.account_id).first()
        if order is None:
            logger.error('%s callback for an order that does not exist: %s',
                         cls.__name__, transaction.account_id)
        return order


class ClickWebhookAPIView(PaidByWebhook, BaseClickWebhookView):
    """Single Click callback endpoint; tolov routes Prepare/Complete internally.

    Mounted by us, at the path Click was given, which is why moving off
    click-pkg did not mean telling Click anything (§17 #253). The path is
    asserted by a test, because breaking it fails silently (§12 risk #2).
    """

    def post(self, request, *args, **kwargs):
        """Click's callback, with the answers tolov gets wrong put right.

        tolov answers Click's Prepare for an order already paid with success,
        and so lets Click charge the card a second time; and its Complete for
        a second charge on such an order with success, so the second sum is
        kept with nothing to show for it. Click's own code for both is -4,
        "already paid", and an error at Complete is what makes Click give the
        money back (§17 #395).

        tolov also fails on a Complete that reports a failed payment: it
        writes "Error code: ..." into an integer column, raises, and answers
        -7. Click asks for the transaction to be cancelled and -9 answered,
        which is done here (§17 #396).

        All of it is asked only once the signature holds, so an unsigned
        caller learns nothing about an order. A successful Complete also
        carries ``merchant_confirm_id``, which Click's protocol lists in that
        answer and click-pkg sent.
        """
        answered = self._answer_first(request.POST.dict())
        if answered is not None:
            return answered
        response = super().post(request, *args, **kwargs)
        return self._with_confirm_id(request.POST.get('action'), response)

    def _answer_first(self, params):
        """Click's answer where tolov's would be wrong, or None to let tolov answer."""
        try:
            self._check_auth(params)
            order = super()._find_account(params.get('merchant_trans_id'))
            error = int(params.get('error') or 0)
        except (PermissionDenied, AccountNotFound, ValueError):
            return None          # tolov answers these itself: -1, -5, -8
        action = params.get('action')
        if action == '1' and error < 0:
            return self._failed(params, order, error)
        if action == '0':
            paid = order.status in SOLD
        elif action == '1':
            # Another charge already paid this order. Click retrying the same
            # Complete is not that: it is answered as before.
            paid = (PaymentTransaction._default_manager
                    .filter(gateway=PaymentTransaction.CLICK,
                            account_id=str(order.pk),
                            state=PaymentTransaction.SUCCESSFULLY)
                    .exclude(transaction_id=params.get('click_trans_id'))
                    .exists())
        else:
            return None
        if not paid:
            return None
        logger.warning('Click charge %s refused: order %s is already paid',
                       params.get('click_trans_id'), order.order_no or order.pk)
        return self._answer(params, -4, 'Already paid')

    def _failed(self, params, order, error):
        """A Complete in which Click reports that the payment failed.

        Nothing was charged. The transaction Prepare made is cancelled with
        Click's error code as its reason, and Click is told -9, as its
        protocol asks. The order is left as it is: still awaiting payment, so
        the customer can try again from the same page, and cancelled after
        three days if nobody pays (§17 #373), as before. A transaction that
        was already completed is Click's -4, and one Click never prepared is
        its -6.
        """
        click_trans_id = params.get('click_trans_id')
        with transaction.atomic():
            charge = (PaymentTransaction._default_manager.select_for_update()
                      .filter(gateway=PaymentTransaction.CLICK,
                              transaction_id=click_trans_id)
                      .first())
            if charge is None:
                return self._answer(params, -6, 'Transaction does not exist')
            if charge.state == PaymentTransaction.SUCCESSFULLY:
                return self._answer(params, -4, 'Already paid')
            charge.mark_as_cancelled(reason=error)
        logger.info('Click payment %s for order %s failed at Click (error %s)',
                    click_trans_id, order.order_no or order.pk, error)
        return self._answer(params, -9, 'Transaction cancelled')

    @staticmethod
    def _answer(params, error, note):
        """One of Click's error answers, naming the transaction and the order."""
        return JsonResponse({
            'click_trans_id': params.get('click_trans_id'),
            'merchant_trans_id': params.get('merchant_trans_id'),
            'error': error,
            'error_note': note,
        })

    @staticmethod
    def _with_confirm_id(action, response):
        """The Complete answer with ``merchant_confirm_id``, when it succeeded."""
        if action != '1':
            return response
        try:
            body = json.loads(response.content)
        except ValueError:
            return response
        if body.get('error') != 0 or 'merchant_prepare_id' not in body:
            return response
        body['merchant_confirm_id'] = body['merchant_prepare_id']
        return JsonResponse(body, status=response.status_code)

    def _find_account(self, merchant_trans_id):
        """The order, unless Click is asking to start a payment for a cancelled one.

        Click's Prepare (action 0) comes before the card is charged, and an
        order tolov cannot find is answered there with Click's own "not
        found", -5, which stops the payment. Complete (action 1) comes after
        the charge and is left alone. See :meth:`refuse_cancelled`.
        """
        order = super()._find_account(merchant_trans_id)
        if self.request.POST.get('action') == '0':
            self.refuse_cancelled(order)
        return order


class PaymeWebhookAPIView(PaidByWebhook, BasePaymeWebhookView):
    """Payme's JSON-RPC callback endpoint.

    Payme quotes tiyin; tolov multiplies `total_price` by 100 before comparing,
    so the amount check needs nothing from us beyond `AMOUNT_FIELD`.
    """

    def before_check_perform_transaction(self, params, account):
        """Payme's question before it charges: may this order be paid for?

        Not if it was cancelled. tolov turns the exception into Payme's own
        "account not found". See :meth:`refuse_cancelled`.
        """
        self.refuse_cancelled(account)


class OctoWebhookAPIView(PaidByWebhook, BaseOctoWebhookView):
    """Octo's notification endpoint.

    Octo signs its callbacks `sha1(unique_key + payment_uuid + status)`, which
    tolov verifies from `OCTO_UNIQUE_KEY` — so that setting is not optional
    decoration: without it a forged notification is indistinguishable from a
    real one.
    """


# ---------- viewing an order ----------

@login_required
def order_detail(request, pk):
    """Order detail page, with per-line totals computed for the template."""
    # `variant__size` as well as the product and its photographs: the template
    # prints the size of every line, and without it that was a query per line
    # (§9 Phase 9 item 7).
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related(
            'cart__cart_items__variant__product__images',
            'cart__cart_items__variant__size'),
        pk=pk, user=request.user,
    )
    for it in order.cart.cart_items.all():
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
    # The parcel at Uzpost, as the shop last read it: pages read the database,
    # never Uzpost (§9 Phase 22 item 13).
    shipment = order.shipments.filter(cancelled_at__isnull=True,
                                      uzpost_id__isnull=False).first()
    return render(request, 'payment/order_detail.html', {
        'order': order,
        'shipment': shipment,
        'shipment_history': shipment.history.all() if shipment else (),
        'pay': _pay_context(request, order),
    })


@login_required
def order_status(request, pk):
    """Lightweight order-status page (used for post-payment status checks)."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, 'payment/status.html', {
        'order': order, 'pay': _pay_context(request, order)})


# ---------- cancel ----------

@login_required
@require_POST
def order_cancel(request, pk):
    """Cancel an order that is still awaiting payment."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if services.cancel_order(order):
        # By the number the customer knows it by - the one on the order page,
        # in the terms and on the parcel - not by its database id (§18 #39).
        messages.success(request, _("%(no)s raqamli buyurtma bekor qilindi.")
                         % {'no': order.order_no or order.pk})
    else:
        messages.error(request, _("Buyurtmani bekor qilib boʻlmadi."))
    return redirect('order_status', pk=order.id)
