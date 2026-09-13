"""Checkout, Click payment start/webhook, and order views."""
import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from click_up.views import ClickWebhook

from core.i18n import tfield
from .models import DeliveryOption, District, Order, PaymentOption, Region
from user.models import phone_regex
from . import services


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
            bucket[d.kind].append({'id': d.pk, 'name': tfield(d, 'name')})

    return {
        'delivery_options': list(DeliveryOption.objects.filter(is_active=True)),
        'payment_options': list(PaymentOption.objects.filter(is_active=True)),
        'regions': regions,
        # Keyed by region id, split by kind, so the drawer can put Tumanlar and
        # Shaharlar under their own headings (§17 #87).
        'districts_json': json.dumps(by_region, ensure_ascii=False),
        'google_maps_key': settings.GOOGLE_MAPS_API_KEY,
    }


def _read_delivery(post):
    """Pull the delivery fields out of a POST. Returns (kwargs, option).

    Nothing from the branch the customer did not pick is carried forward: a home
    order keeps no region, district or index, and a branch order keeps no
    coordinates. That is what stops a stale value from a hidden half of the form
    reaching the database and quietly contradicting the rest of the order.
    """
    option = DeliveryOption.objects.filter(
        code=post.get('delivery_option', '').strip(), is_active=True
    ).first()

    kwargs = {
        'delivery_option': option,
        'region': None, 'district': None, 'postal_index': '',
        'location_note': '', 'address_source': '',
        'latitude': None, 'longitude': None,
    }
    if option is None:
        return kwargs, None

    if option.requires_branch:
        kwargs['region'] = Region.objects.filter(pk=_int(post.get('region')),
                                                 is_active=True).first()
        kwargs['district'] = District.objects.filter(pk=_int(post.get('district')),
                                                     is_active=True).first()
        kwargs['postal_index'] = post.get('postal_index', '').strip()
        # Only meaningful for the Boshqa escape; ignored otherwise, so a stray
        # value cannot end up on a perfectly ordinary order.
        if kwargs['district'] is not None and kwargs['district'].kind == District.Kind.OTHER:
            kwargs['location_note'] = post.get('location_note', '').strip()[:160]
    else:
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

    context = {'items': items, 'subtotal': subtotal, 'item_count': item_count}
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
    address = post.get('address', '').strip()
    notes = post.get('notes', '').strip()

    delivery_kwargs, option = _read_delivery(post)
    delivery = Decimal(option.price_for_items(item_count)) if option else Decimal('0')

    form_data = {
        'name': name, 'phone': phone, 'address': address, 'notes': notes,
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

    try:
        phone_regex(phone)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return again(form_data, delivery)

    # One validator for both paths. Building an unsaved Order and asking it is
    # cheaper than repeating the rules, and it guarantees the view and
    # Order.clean can never disagree about what a valid order is.
    probe = Order(address=address, **delivery_kwargs)
    try:
        probe.clean()
    except ValidationError as e:
        for message in e.messages:
            messages.error(request, message)
        return again(form_data, delivery)

    try:
        order = services.create_order_from_cart(
            request.user, cart,
            phone=phone, address=address, notes=notes,
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
    """Generate a Click pay link and redirect to it (only while still PAYING)."""
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.status != Order.Status.PAYING:
        messages.info(request, _("Bu buyurtma uchun toʻlov holati "
                                 "allaqachon oʻzgargan."))
        return redirect('order_status', pk=order.id)

    return_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
    paylink = services.generate_click_paylink(order, return_url)
    return redirect(paylink)


class ClickWebhookAPIView(ClickWebhook):
    """Single Click callback endpoint; click_up routes Prepare/Complete internally."""
    def successfully_payment(self, params):
        services.apply_successful_payment(params.click_trans_id)

    def cancelled_payment(self, params):
        services.apply_cancelled_payment(params.click_trans_id)


# ---------- viewing an order ----------

@login_required
def order_detail(request, pk):
    """Order detail page, with per-line totals computed for the template."""
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product__images'),
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
        messages.success(request, _("#%(no)s bekor qilindi.") % {'no': order.id})
    else:
        messages.error(request, _("Buyurtmani bekor qilib boʻlmadi."))
    return redirect('order_status', pk=order.id)
