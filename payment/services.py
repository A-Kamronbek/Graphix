"""Checkout and payment operations.

Turns an open cart into an Order under a row lock, generates the pay link for
whichever method the order names, applies payment-status changes from the
gateways' webhook callbacks, and moves stock as orders are paid for or
cancelled.

Four payment methods: Click, Payme, Octo and cash. Only two functions know
about gateways at all. `generate_paylink` picks the client and is the one
place that handles a gateway refusing; `apply_successful_payment` knows none
of them, because the webhook resolves the order before calling it.

Click and Payme build their pay links locally. Octo calls out over HTTP, so a
gateway having a bad day has to cost the customer a retry rather than a 500
(§17 #266).
"""
import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.conf import settings
from tolov import ClickGateway, OctoGateway, PaymeGateway

from cart.models import Cart
from core import legal, telegram
from product.models import Variant
from .models import Order, location_text

#: Module logger, because every external call on this site logs through one
#: and returns rather than raising (§4, the `core/sms.py` pattern).
logger = logging.getLogger(__name__)


class EmptyCart(Exception):
    """Raised when checkout is attempted on a missing or empty cart."""


class CartAlreadyCheckedOut(Exception):
    """Raised when the cart already has an Order; carries that existing order."""
    def __init__(self, existing_order):
        super().__init__("Cart already checked out")
        self.existing_order = existing_order


class OffSaleItems(Exception):
    """Raised when the cart holds lines that are no longer on sale; carries them."""
    def __init__(self, lines):
        super().__init__("Cart holds lines that are off sale")
        self.lines = lines


def get_open_cart(user):
    """Return the user's open cart, or None."""
    return Cart.objects.filter(user=user, status=True).first()


def _create_order(**fields):
    """Create an Order, retrying if its generated ``order_no`` collides.

    ``Order.save()`` derives the number from the highest one already used today,
    so two checkouts landing in the same instant can pick the same value. Each
    attempt runs in its own savepoint: an IntegrityError rolls back only that
    savepoint, leaving the caller's transaction usable, and the retry regenerates
    the number from a now-committed row.
    """
    last_error = None
    for _ in range(5):
        try:
            with transaction.atomic():
                return Order.objects.create(**fields)
        except IntegrityError as exc:
            last_error = exc
    raise last_error


def create_order_from_cart(user, cart, *, phone, address, notes, payment_method,
                           delivery=Decimal('0'), delivery_option=None,
                           region=None, district=None, postal_index='',
                           location_note='', address_source='',
                           latitude=None, longitude=None, recipient_name=''):
    """Create an Order from the cart atomically, then close the cart.

    The cart row is locked with ``select_for_update`` and the total is computed
    *after* the lock from the locked line items, so two concurrent checkouts of
    the same cart can't race into duplicate orders or a stale total. An
    already-closed cart raises CartAlreadyCheckedOut (if an order exists) or
    EmptyCart, and a cart holding a line that is no longer on sale raises
    OffSaleItems before anything is written.

    When a ``delivery_option`` is given, its fee is computed from the locked line
    count and replaces ``delivery``. Either way the destination is frozen as text
    into ``location_snapshot`` at this moment — region and district for both
    methods, then either the postal index or the street address — so a district
    renamed a year later cannot rewrite where the parcel was sent. Callers that
    pass a bare ``delivery`` amount keep working exactly as before.

    ``recipient_name`` is who the parcel is addressed to. It is only stored:
    it takes no part in the lock or the total, and a caller that does not
    pass it gets a blank, as every order did before it existed.

    The version of the terms and of the privacy policy in force at this moment
    is stamped onto the order as well. The checkout says that pressing the
    button accepts both, and this is the only place an order is made from a
    checkout, so a caller cannot forget it (§17 #272).
    """
    with transaction.atomic():
        # Lock the cart row for the duration of the transaction.
        locked_cart = (
            Cart.objects.select_for_update()
            .filter(pk=cart.pk, user=user)
            .first()
        )

        if locked_cart is None or not locked_cart.status:
            existing = Order.objects.filter(cart_id=cart.pk).first()
            if existing:
                raise CartAlreadyCheckedOut(existing)
            raise EmptyCart()

        locked_lines = locked_cart.cart_items.all()
        if not locked_lines:
            raise EmptyCart()
        # The checkout view turns such a cart away before the form; this asks
        # the same question under the lock, so a product switched off in
        # between is still not sold (§17 #294). A separate query, so the lines
        # the total is summed from are untouched.
        off_sale = [line for line in
                    locked_cart.cart_items.select_related('variant__product')
                    if not line.variant.is_on_sale]
        if off_sale:
            raise OffSaleItems(off_sale)
        if delivery_option is not None:
            # Priced from the locked lines, for the same reason the total is.
            item_count = sum(it.quantity for it in locked_lines)
            delivery = Decimal(delivery_option.price_for_items(item_count))
        # Total is summed from the LOCKED lines, after the lock, to avoid desync.
        locked_total = sum(
            ((it.price_stat or Decimal('0')) * it.quantity for it in locked_lines),
            Decimal('0'),
        ) + delivery

        order = _create_order(
            user=user,
            cart=locked_cart,
            phone=phone,
            recipient_name=recipient_name,
            address=address,
            notes=notes,
            payment_method=payment_method,
            total_price=locked_total,
            status=Order.Status.PAYING,
            delivery_option=delivery_option,
            delivery_price=delivery,
            region=region,
            district=district,
            postal_index=postal_index,
            location_note=location_note,
            location_snapshot=location_text(region, district, postal_index,
                                            location_note, address),
            address_source=address_source,
            latitude=latitude,
            longitude=longitude,
            # Both consent columns, from the one lookup the signup form also
            # uses - so a third document added later is recorded on orders
            # without anybody having to remember this call.
            **legal.accepted_versions(),
        )
        locked_cart.status = False
        locked_cart.save(update_fields=['status'])

        # Nothing is sent here. The shop's Telegram notification goes when the
        # payment arrives, not when the order is written (§17 #237): an order
        # that is still `paying` may never be paid for, and a notification for
        # one is a parcel the owner goes looking for and does not find.

    return order


def generate_click_paylink(order, return_url):
    """Create a Click hosted-payment link for the order.

    ``amount`` is passed in so'm (UZS); ``total_price`` is already whole so'm, so
    no tiyin conversion is needed here.
    """
    gateway = ClickGateway(service_id=settings.CLICK_SERVICE_ID,
                           merchant_id=settings.CLICK_MERCHANT_ID)
    return gateway.create_payment(
        id=order.id,
        amount=order.total_price,
        return_url=return_url,
    )


class PaymentMethodUnavailable(Exception):
    """Raised when an order names a method the shop cannot start a payment for.

    Its own exception rather than None, because the two cases the caller has
    to tell apart — "this method has no online step" (cash) and "this method
    is configured wrong" — both end in the customer being sent somewhere, and
    silently redirecting to a blank page is how the first bug in a payment
    flow hides.

    Permanent, as far as this customer is concerned: retrying in a minute
    changes nothing. :class:`PaymentGatewayError` is the other kind.
    """


class PaymentGatewayError(Exception):
    """Raised when a gateway was asked for a pay link and did not give one.

    A refused request, a network failure, or a reply with no link in it. The
    customer is told something different from the case above — try again
    shortly, rather than this method has no online payment — because the
    order is still PAYING and the method will very likely work in an hour.
    """


#: Which settings each online method needs before it can build a pay link.
#: Cash is absent on purpose: it needs nothing, has no online step, and
#: `generate_paylink` never reaches a gateway for it.
GATEWAY_CREDENTIALS = {
    Order.PaymentMethod.CLICK: ('CLICK_SERVICE_ID', 'CLICK_MERCHANT_ID'),
    Order.PaymentMethod.PAYME: ('PAYME_ID', 'PAYME_KEY'),
    Order.PaymentMethod.OCTO: ('OCTO_SHOP_ID', 'OCTO_SECRET'),
}

#: What a method additionally needs once it is handling real money. Octo signs
#: its callbacks `sha1(unique_key + payment_uuid + status)`, and tolov refuses
#: to construct the webhook at all without the key unless test mode is on —
#: so with it missing in production a customer could pay and the callback
#: would raise before it ever reached us. Shop id and secret are enough to
#: *take* a payment and not enough to *confirm* one, which is the worst shape
#: a payment integration can be in (§17 #267).
LIVE_ONLY_CREDENTIALS = {
    Order.PaymentMethod.OCTO: ('OCTO_UNIQUE_KEY',),
}


def octo_test_mode():
    """Whether Octo is in test mode, read from the dict tolov itself reads.

    `TOLOV['OCTO_BANK']['TEST_MODE']` is what the webhook consults. Reading
    `DEBUG` separately here would be a second answer to the same question,
    and the two halves disagreeing is how a link built as a test payment
    meets a webhook expecting a live one. One place, so the day there is a
    staging server (§18 #46) only the setting changes.
    """
    return bool(settings.TOLOV.get('OCTO_BANK', {}).get('TEST_MODE', False))


def method_is_configured(method):
    """Whether the shop holds the credentials this method needs.

    Cash is configured by definition; a method not in the table is not.

    One function rather than a check wherever somebody wants the answer,
    because two answers that drift apart is exactly how a method comes to
    look ready in the panel and fail at the checkout (§17 #266).
    """
    if method == Order.PaymentMethod.CASH:
        return True
    names = GATEWAY_CREDENTIALS.get(method)
    if not names:
        return False
    if method != Order.PaymentMethod.OCTO or not octo_test_mode():
        # Test mode is the only state in which the live-only keys are
        # genuinely optional, and it is tolov that decides that, not us.
        names = names + LIVE_ONLY_CREDENTIALS.get(method, ())
    return all(str(getattr(settings, name, '') or '').strip() for name in names)


def _build_paylink(order, return_url, method):
    """Ask this method's gateway for a link, raising whatever the gateway raises.

    Split out so the error handling in `generate_paylink` reads as one thing:
    everything in here is somebody else's library, and none of it can be
    trusted to fail politely.

    Each gateway is constructed per call rather than held at module level: the
    credentials come from settings, and a module-level client would read them
    once at import and cache whatever was there then.
    """
    if method == Order.PaymentMethod.CLICK:
        return generate_click_paylink(order, return_url)

    if method == Order.PaymentMethod.PAYME:
        gateway = PaymeGateway(payme_id=settings.PAYME_ID,
                               payme_key=settings.PAYME_KEY)
        # Payme quotes tiyin, so'm * 100. tolov does this multiplication for
        # us when it *checks* a callback, and not when it builds a link.
        return gateway.create_payment(
            id=order.id, amount=int(order.total_price) * 100,
            return_url=return_url)

    # `octo_shop_id` is typed int. The setting comes from the environment as
    # text and is blank until the owner has one, so it is coerced here rather
    # than at import — `int("")` raises, and a missing key must not stop the
    # site booting (§17 #264).
    #
    # `is_test_mode` is passed for one reason: it becomes the `test` flag in
    # Octo's request body, and that flag decides whether real money moves.
    # Left off, every link built on a developer's laptop is a live payment.
    # It comes from the same setting the webhook reads, so the two halves of
    # one payment cannot disagree about which kind it is (§17 #266, #267).
    gateway = OctoGateway(
        octo_shop_id=int(settings.OCTO_SHOP_ID or 0),
        octo_secret=settings.OCTO_SECRET,
        is_test_mode=octo_test_mode())
    return gateway.create_payment(
        id=order.id, amount=order.total_price, return_url=return_url)


def generate_paylink(order, return_url):
    """The hosted-payment link for whichever method the order was placed with.

    One place that knows which gateway builds which link, so `payment_start`
    does not grow a branch per method (§9 Phase 14 item 5), and one place
    that knows a gateway can say no. Three outcomes, and the caller has to
    tell them apart: a link, PaymentMethodUnavailable (cash, or nothing
    configured — permanent), or PaymentGatewayError (asked and refused —
    worth retrying).

    §4's rule that an external call never breaks a request applies here as
    much as it does to SMS. It did not used to be needed: Click and Payme
    build their links locally. Octo calls out, and tolov reads its reply as
    `response["data"]["octo_pay_url"]` while Octo answers *every* error with
    `"data": null` — so before this, a wrong shop id 500'd the checkout
    rather than degrading it (§17 #266).
    """
    method = order.payment_method
    if method not in GATEWAY_CREDENTIALS:
        # Cash, and anything else with no online step.
        raise PaymentMethodUnavailable(method)

    if not method_is_configured(method):
        # Asked before calling out, not after. Octo answers a blank shop id
        # with an error rather than a link, and a round-trip to be told what
        # settings could have said is a round-trip the customer waits for.
        logger.error('Order %s names %s, which has no credentials configured.',
                     order.pk, method)
        raise PaymentMethodUnavailable(method)

    try:
        paylink = _build_paylink(order, return_url, method)
    except Exception:
        # Everything, deliberately — the `core/sms.py` pattern (§4). A
        # gateway having a bad day costs one checkout a retry, not a 500.
        logger.exception('Pay link for order %s failed at %s.', order.pk, method)
        raise PaymentGatewayError(method)

    if not paylink:
        # tolov returns '' when it understood the reply but found no link in
        # it. `redirect('')` is a bug of its own, so it stops here.
        logger.error('%s returned an empty pay link for order %s.',
                     method, order.pk)
        raise PaymentGatewayError(method)

    return paylink


def _move_stock(order, sign):
    """Add ``sign`` * quantity to each ordered variant's stock.

    ``sign`` is -1 when an order is paid for and +1 when a paid order is undone.
    One ``UPDATE`` per variant with an F() expression, never a Python-side
    read-modify-write, so a concurrent checkout can't lose a decrement.
    ``Greatest(..., 0)`` is a floor: if the owner lowered stock by hand after the
    order was placed, the column must not go negative.
    """
    for item in order.cart.cart_items.all():
        Variant.objects.filter(pk=item.variant_id).update(
            stock=Greatest(F('stock') + Value(sign * item.quantity), Value(0))
        )


def apply_successful_payment(order):
    """Mark ``order`` PAID (idempotent). The only place an order becomes paid.

    The status check is what makes it idempotent: a gateway can replay a
    callback, and stock must only come down once.

    Takes the order rather than a gateway's transaction id. It used to take a
    Click transaction id and look the order up through click-pkg's own table,
    which made this function know about one gateway; resolving the order is
    the webhook's job now, and this stays the single place the status moves
    (§17 #253).
    """
    if order.status != Order.Status.PAID:
        with transaction.atomic():
            _move_stock(order, -1)
            order.status = Order.Status.PAID
            order.save(update_fields=['status', 'updated_at'])
            # Queued inside the transaction and sent after it commits: a
            # notification for a payment that then rolled back is worse than
            # none, and an HTTP call inside the transaction would hold the
            # order's row open for the length of it (§12 risk #17).
            telegram.notify_paid_order(order)


def apply_cancelled_payment(order):
    """Mark ``order`` CANCELLED unless it is already paid or cancelled.

    Leaves orders that are already paid or cancelled untouched — so no stock
    moves here: an order that never reached PAID never took any.

    The old version re-read click-pkg's transaction row and acted only if its
    state was CANCELLED. That guard is not lost: tolov calls its
    ``cancelled_payment`` hook only for a cancellation, so the call itself is
    the signal, and the status check below is what stops a replay undoing a
    paid order.
    """
    if order.status not in (Order.Status.PAID, Order.Status.CANCELLED):
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])


def cancel_order(order):
    """Cancel an order still awaiting payment; return whether the status changed.

    PAYING only, so there is no stock to give back. Cancelling an order that was
    already paid for is a staff action — see :func:`cancel_paid_order`.
    """
    if order.status == Order.Status.PAYING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        return True
    return False


def cancel_paid_order(order):
    """Cancel an order that has already been paid for, returning its stock.

    Separate from :func:`cancel_order` on purpose: that one is reachable from the
    storefront, and a customer must not be able to cancel a paid order. Returns
    whether the status changed.
    """
    if order.status in (Order.Status.CANCELLED, Order.Status.PAYING):
        return False
    with transaction.atomic():
        _move_stock(order, +1)
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
    return True
