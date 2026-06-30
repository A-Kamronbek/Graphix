"""Checkout and Click payment operations.

Turns an open cart into an Order under a row lock, generates the Click pay link,
and applies payment-status changes from Click's webhook callbacks.
"""
from decimal import Decimal

from django.db import transaction
from django.conf import settings
from click_up import ClickUp
from click_up.models import ClickTransaction

from cart.models import Cart
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


def create_order_from_cart(user, cart, *, phone, address, notes, payment_method,
                           delivery=Decimal('0')):
    """Create an Order from the cart atomically, then close the cart.

    The cart row is locked with ``select_for_update`` and the total is computed
    *after* the lock from the locked line items, so two concurrent checkouts of
    the same cart can't race into duplicate orders or a stale total. An
    already-closed cart raises CartAlreadyCheckedOut (if an order exists) or
    EmptyCart.
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
        # Total is summed from the LOCKED lines, after the lock, to avoid desync.
        locked_total = sum(
            ((it.price_stat or Decimal('0')) * it.quantity for it in locked_lines),
            Decimal('0'),
        ) + delivery

        order = Order.objects.create(
            user=user,
            cart=locked_cart,
            phone=phone,
            address=address,
            notes=notes,
            payment_method=payment_method,
            total_price=locked_total,
            status=Order.Status.PAYING,
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


def apply_successful_payment(click_trans_id):
    """Mark the order PAID for a completed Click transaction (idempotent)."""
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    order = Order.objects.get(id=transaction.account_id)
    if order.status != Order.Status.PAID:
        order.status = Order.Status.PAID
        order.save(update_fields=['status', 'updated_at'])


def apply_cancelled_payment(click_trans_id):
    """Mark the order CANCELLED for a cancelled Click transaction.

    Leaves orders that are already paid or cancelled untouched.
    """
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    if transaction.state == ClickTransaction.CANCELLED:
        order = Order.objects.get(id=transaction.account_id)
        if order.status not in (Order.Status.PAID, Order.Status.CANCELLED):
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])


def cancel_order(order):
    """Cancel an order still awaiting payment; return whether the status changed."""
    if order.status == Order.Status.PAYING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        return True
    return False
