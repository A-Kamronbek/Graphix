"""Checkout, Click payment start/webhook, and order views."""
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import translation
from django.utils.translation import gettext as _
from tolov.integrations.django.webhooks import (ClickWebhook, OctoWebhook,
                                                PaymeWebhook)

from core.i18n import tfield
from .models import (DeliveryOption, District, Order, PaymentOption, Region,
                     RECIPIENT_NAME_MAX)
from user.models import phone_regex
from . import services

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
    regions = list(Region.objects.filter(is_active=True))
    districts = (District.objects.filter(is_active=True, region__is_active=True)
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
            })

    return {
        'delivery_options': list(DeliveryOption.objects.filter(is_active=True)),
        'payment_options': list(PaymentOption.objects.filter(is_active=True)),
        'regions': regions,
        # Keyed by region id, split by kind, so the drawer can put Tumanlar and
        # Shaharlar under their own headings (§17 #87).
        'districts_json': json.dumps(by_region, ensure_ascii=False),
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


def _read_delivery(post):
    """Pull the delivery fields out of a POST. Returns (kwargs, option).

    Region and district are read for **both** methods (§17 #106) — the courier
    needs them as much as the post office does. Everything below them still
    belongs to one branch only: a home order keeps no postal index, and a branch
    order keeps no address and no coordinates. That is what stops a stale value
    from the hidden half of the form reaching the database and quietly
    contradicting the rest of the order.
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

    if option.requires_branch:
        kwargs['postal_index'] = post.get('postal_index', '').strip()
    else:
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
        messages.error(request, _("Savat boʻsh."))
        return redirect('cart')

    items_qs = (
        cart.cart_items
        .select_related('variant__product', 'variant__size', 'variant__colour')
        .prefetch_related('variant__product__images')
    )
    items = _annotate_lines(items_qs)
    subtotal = sum((it.line_total for it in items), Decimal('0'))
    item_count = sum(it.quantity for it in items)

    context = {'items': items, 'subtotal': subtotal, 'item_count': item_count,
               'recipient_name_max': RECIPIENT_NAME_MAX}
    context.update(_delivery_context())

    def again(form_data, delivery=Decimal('0')):
        """Re-render the form with what the customer typed still in it."""
        context.update({'delivery': delivery, 'total': subtotal + delivery,
                        'form_data': form_data})
        return render(request, 'payment/checkout.html', context)

    if request.method != 'POST':
        default = next((o for o in context['delivery_options']), None)
        delivery = Decimal(default.price_for_items(item_count)) if default else Decimal('0')
        return again({'delivery_option': default.code if default else ''}, delivery)

    post = request.POST
    name = post.get('name', '').strip()
    phone = post.get('phone', '').strip()
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
        'postal_index': delivery_kwargs['postal_index'],
        'location_note': delivery_kwargs['location_note'],
        'address_source': delivery_kwargs['address_source'],
        'latitude': delivery_kwargs['latitude'],
        'longitude': delivery_kwargs['longitude'],
    }

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

    try:
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
            **delivery_kwargs,
        )
    except services.CartAlreadyCheckedOut as e:
        messages.info(request, _("Buyurtma allaqachon rasmiylashtirilgan."))
        return redirect('payment', order_id=e.existing_order.id)
    except services.EmptyCart:
        messages.error(request, _("Savat boʻsh."))
        return redirect('cart')

    messages.success(request, _("Buyurtma qabul qilindi. Toʻlovni amalga oshiring."))
    return redirect('payment', order_id=order.id)


# ---------- payment (Click) ----------

@login_required
def payment(request, order_id):
    """Show the payment page for an order."""
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product'),
        pk=order_id, user=request.user,
    )
    return render(request, 'payment/payment.html', {'order': order})


@login_required
@require_POST
def payment_start(request, order_id):
    """Generate the pay link for this order's method and redirect to it.

    Only while the order is still PAYING. Which gateway builds the link is
    `services.generate_paylink`'s business, not this view's.
    """
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.status != Order.Status.PAYING:
        messages.info(request, _("Bu buyurtma uchun toʻlov holati "
                                 "allaqachon oʻzgargan."))
        return redirect('order_status', pk=order.id)

    return_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
    try:
        paylink = services.generate_paylink(order, return_url)
    except services.PaymentMethodUnavailable:
        # Cash has no online step, and a method whose credentials are blank
        # cannot make a link either. Both end here, and both are told plainly
        # rather than redirected at a gateway that will show a broken page.
        messages.info(request, _("Bu toʻlov usuli uchun onlayn toʻlov yoʻq."))
        return redirect('order_status', pk=order.id)
    return redirect(paylink)


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


class ClickWebhookAPIView(PaidByWebhook, ClickWebhook):
    """Single Click callback endpoint; tolov routes Prepare/Complete internally.

    Mounted by us, at the path Click was given, which is why moving off
    click-pkg did not mean telling Click anything (§17 #253). The path is
    asserted by a test, because breaking it fails silently (§12 risk #2).
    """


class PaymeWebhookAPIView(PaidByWebhook, PaymeWebhook):
    """Payme's JSON-RPC callback endpoint.

    Payme quotes tiyin; tolov multiplies `total_price` by 100 before comparing,
    so the amount check needs nothing from us beyond `AMOUNT_FIELD`.
    """


class OctoWebhookAPIView(PaidByWebhook, OctoWebhook):
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
    return render(request, 'payment/order_detail.html', {'order': order})


@login_required
def order_status(request, pk):
    """Lightweight order-status page (used for post-payment status checks)."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, 'payment/status.html', {'order': order})


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
