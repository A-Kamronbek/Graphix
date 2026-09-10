"""Checkout and Click payment operations.

Turns an open cart into an Order under a row lock, generates the Click pay link,
applies payment-status changes from Click's webhook callbacks, and moves stock as
orders are paid for or cancelled.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.conf import settings
from click_up import ClickUp
from click_up.models import ClickTransaction

from cart.models import Cart
from product.models import Variant
from .models import Order


class EmptyCart(Exception):
    """Raised when checkout is attempted on a missing or empty cart."""


class CartAlreadyCheckedOut(Exception):
    """Raised when the cart already has an Order; carries that existing order."""
    def __init__(self, existing_order):
        super().__init__("Cart already checked out")
        self.existing_order = existing_order


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
                           pickup_point=None, latitude=None, longitude=None):
    """Create an Order from the cart atomically, then close the cart.

    The cart row is locked with ``select_for_update`` and the total is computed
    *after* the lock from the locked line items, so two concurrent checkouts of
    the same cart can't race into duplicate orders or a stale total. An
    already-closed cart raises CartAlreadyCheckedOut (if an order exists) or
    EmptyCart.

    When a ``delivery_option`` is given, its fee is computed from the locked line
    count and replaces ``delivery``, and the chosen branch is frozen into
    ``pickup_snapshot``. Callers that pass a bare ``delivery`` amount keep working
    exactly as before.
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
            address=address,
            notes=notes,
            payment_method=payment_method,
            total_price=locked_total,
            status=Order.Status.PAYING,
            delivery_option=delivery_option,
            delivery_price=delivery,
            pickup_point=pickup_point,
            pickup_snapshot=pickup_point.snapshot() if pickup_point else '',
            latitude=latitude,
            longitude=longitude,
        )
        locked_cart.status = False
        locked_cart.save(update_fields=['status'])

    return order


def generate_click_paylink(order, return_url):
    """Create a Click hosted-payment link for the order.

    ``amount`` is passed in so'm (UZS); ``total_price`` is already whole so'm, so
    no tiyin conversion is needed here.
    """
    click_up = ClickUp(service_id=settings.CLICK_SERVICE_ID,
                       merchant_id=settings.CLICK_MERCHANT_ID)
    return click_up.initializer.generate_pay_link(
        id=order.id,
        amount=order.total_price,
        return_url=return_url,
    )


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


def apply_successful_payment(click_trans_id):
    """Mark the order PAID for a completed Click transaction (idempotent).

    The status check is what makes it idempotent: Click can replay a callback, and
    stock must only come down once. Local name ``click_txn`` rather than
    ``transaction`` so ``django.db.transaction`` stays reachable here.
    """
    click_txn = ClickTransaction.objects.get(transaction_id=click_trans_id)
    order = Order.objects.get(id=click_txn.account_id)
    if order.status != Order.Status.PAID:
        with transaction.atomic():
            _move_stock(order, -1)
            order.status = Order.Status.PAID
            order.save(update_fields=['status', 'updated_at'])


def apply_cancelled_payment(click_trans_id):
    """Mark the order CANCELLED for a cancelled Click transaction.

    Leaves orders that are already paid or cancelled untouched — so no stock
    moves here: an order that never reached PAID never took any.
    """
    click_txn = ClickTransaction.objects.get(transaction_id=click_trans_id)
    if click_txn.state == ClickTransaction.CANCELLED:
        order = Order.objects.get(id=click_txn.account_id)
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
