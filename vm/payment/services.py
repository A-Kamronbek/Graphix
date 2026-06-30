from decimal import Decimal

from django.db import transaction
from django.conf import settings
from click_up import ClickUp
from click_up.models import ClickTransaction

from cart.models import Cart
from .models import Order


class EmptyCart(Exception):
    """"""


class CartAlreadyCheckedOut(Exception):
    def __init__(self, existing_order):
        super().__init__("Cart already checked out")
        self.existing_order = existing_order


def get_open_cart(user):
    return Cart.objects.filter(user=user, status=True).first()


def create_order_from_cart(user, cart, *, phone, address, notes, payment_method,
                           delivery=Decimal('0')):
    with transaction.atomic():
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
    click_up = ClickUp(service_id=settings.CLICK_SERVICE_ID,
                       merchant_id=settings.CLICK_MERCHANT_ID)
    return click_up.initializer.generate_pay_link(
        id=order.id,
        amount=order.total_price,
        return_url=return_url,
    )


def apply_successful_payment(click_trans_id):
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    order = Order.objects.get(id=transaction.account_id)
    if order.status != Order.Status.PAID:
        order.status = Order.Status.PAID
        order.save(update_fields=['status', 'updated_at'])


def apply_cancelled_payment(click_trans_id):
    transaction = ClickTransaction.objects.get(transaction_id=click_trans_id)
    if transaction.state == ClickTransaction.CANCELLED:
        order = Order.objects.get(id=transaction.account_id)
        if order.status not in (Order.Status.PAID, Order.Status.CANCELLED):
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])


def cancel_order(order):
    if order.status == Order.Status.PAYING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        return True
    return False
