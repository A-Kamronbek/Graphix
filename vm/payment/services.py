"""
Payment / order domain logic, kept out of the views.

Views stay thin (parse request, choose template/redirect, set messages); the
rules that touch the database and money live here.
"""
from decimal import Decimal

from django.db import transaction
from django.conf import settings
from click_up import ClickUp
from click_up.models import ClickTransaction

from cart.models import Cart
from .models import Order


class EmptyCart(Exception):
    """The cart has no lines to turn into an order."""


class CartAlreadyCheckedOut(Exception):
    """A concurrent request already created the order for this cart."""
    def __init__(self, existing_order):
        super().__init__("Cart already checked out")
        self.existing_order = existing_order


def get_open_cart(user):
    """Return the user's currently open cart, or None."""
    return Cart.objects.filter(user=user, status=True).first()


def create_order_from_cart(user, cart, *, phone, address, notes, payment_method,
                           delivery=Decimal('0')):
    """
    Atomically turn an open cart into a PAYING order and close the cart.

    Raises CartAlreadyCheckedOut (carrying the existing order) if a concurrent
    request already converted this cart, or EmptyCart if there's nothing to buy.
    """
    with transaction.atomic():
        # Lock the cart row. A second, near-simultaneous checkout on the same
        # cart (e.g. a double-click) blocks here until the first transaction
        # commits, then re-reads the now-closed status below — instead of both
        # racing to Order.objects.create() and the second hitting an
        # IntegrityError on the OneToOne cart field (a 500 for the user).
        locked_cart = (
            Cart.objects.select_for_update()
            .filter(pk=cart.pk, user=user)
            .first()
        )

        # Already checked out by the concurrent request -> don't create a
        # second Order. Surface the order that already exists.
        if locked_cart is None or not locked_cart.status:
            existing = Order.objects.filter(cart_id=cart.pk).first()
            if existing:
                raise CartAlreadyCheckedOut(existing)
            raise EmptyCart()

        # Recompute the total from the LOCKED cart's lines. The total computed
        # before the lock can be stale: a concurrent cart_add in another tab may
        # have inserted a line between that read and the lock, which would
        # otherwise persist an undercounted order.
        locked_lines = locked_cart.cart_items.all()
        if not locked_lines:
            raise EmptyCart()
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
            status=Order.Status.PAYING,  # straight to "awaiting payment"
        )
        locked_cart.status = False
        locked_cart.save(update_fields=['status'])

    return order


def generate_click_paylink(order, return_url):
    """Build a Click pay link for an order."""
    click_up = ClickUp(service_id=settings.CLICK_SERVICE_ID,
                       merchant_id=settings.CLICK_MERCHANT_ID)
    return click_up.initializer.generate_pay_link(
        id=order.id,
        amount=order.total_price,
        return_url=return_url,
    )


def apply_successful_payment(click_trans_id):
    """Click confirmed the payment -> mark the order PAID."""
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    order = Order.objects.get(id=transaction.account_id)
    if order.status != Order.Status.PAID:
        order.status = Order.Status.PAID
        order.save(update_fields=['status', 'updated_at'])


def apply_cancelled_payment(click_trans_id):
    """Click reported a cancelled/failed payment -> mark the order CANCELLED
    (but never override an order that already completed)."""
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    if transaction.state == ClickTransaction.CANCELLED:
        order = Order.objects.get(id=transaction.account_id)
        if order.status not in (Order.Status.PAID, Order.Status.CANCELLED):
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])


def cancel_order(order):
    """Cancel an order that's still awaiting payment. Returns True if cancelled,
    False if its status no longer allows cancellation."""
    if order.status == Order.Status.PAYING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        return True
    return False
