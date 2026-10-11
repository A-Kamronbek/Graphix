"""Phase 16: a customer types a promo code at checkout and pays less.

A code is one of five kinds: a sum or a share off one item, a sum or a share
off the whole order, or free delivery. The tests are the phase's Definition of
Done written as assertions. Each rule that refuses a code sits beside a
control showing that the same order goes through with a valid one, so a test
cannot pass because every code is refused.

The first class is older than the codes. The panel moved an order's status
without touching stock, so a paid order cancelled by staff kept its stock
taken and one marked paid by hand took none. A code's use is counted in the
same place stock is, so that place had to be right first.
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from core import telegram
from panel.models import OrderStatusChange
from panel.services import set_status
from payment import services
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff


def order_of(user, *lines, status=Order.Status.PAYING, delivery=0):
    """An order of ``lines``, each a ``(variant, quantity)`` pair, never paid."""
    cart = Cart.objects.create(user=user, status=False)
    goods = Decimal('0')
    for variant, quantity in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity,
                                price_stat=variant.price)
        goods += variant.price * quantity
    return Order.objects.create(user=user, cart=cart, phone=user.phone,
                                address='Amir Temur 1', status=status,
                                delivery_price=delivery,
                                total_price=goods + delivery)


def stock_of(variant):
    """The stock of ``variant`` as the database has it now."""
    variant.refresh_from_db()
    return variant.stock


class StaffMovesStockTests(TestCase):
    """Stock follows the order across the line between paid and not paid.

    Whoever moves it: the gateway's callback, the panel, or the Django admin.
    """

    def setUp(self):
        self.staff = make_staff()
        self.customer = make_user('xaridor', '+998901220003')
        _, self.variant = make_product('Zaxira', stock=10)
        self.order = order_of(self.customer, (self.variant, 3))

    def paid(self):
        """The order, paid for through the gateway's own path."""
        services.apply_successful_payment(self.order)
        self.order.refresh_from_db()
        self.assertEqual(stock_of(self.variant), 7)
        return self.order

    def test_staff_cancelling_a_paid_order_puts_its_stock_back(self):
        set_status(self.paid(), Order.Status.CANCELLED, by=self.staff)
        self.assertEqual(stock_of(self.variant), 10)

    def test_the_panel_screen_does_the_same(self):
        self.paid()
        self.client.force_login(self.staff)
        self.client.post(reverse('panel_order_status',
                                 kwargs={'order_no': self.order.order_no}),
                         {'status': 'cancelled'})
        self.assertEqual(stock_of(self.variant), 10)
        self.assertEqual(OrderStatusChange.objects.get().to_status, 'cancelled')

    def test_staff_marking_an_unpaid_order_paid_takes_its_stock(self):
        """A customer who paid some other way, entered by hand."""
        set_status(self.order, Order.Status.PAID, by=self.staff)
        self.assertEqual(stock_of(self.variant), 7)

    def test_an_order_moved_along_after_payment_takes_nothing_more(self):
        order = self.paid()
        for status in (Order.Status.PROCESSING, Order.Status.ON_THE_WAY,
                       Order.Status.DONE):
            set_status(order, status, by=self.staff)
            self.assertEqual(stock_of(self.variant), 7, status)

    def test_cancelling_an_unpaid_order_gives_nothing_back(self):
        set_status(self.order, Order.Status.CANCELLED, by=self.staff)
        self.assertEqual(stock_of(self.variant), 10)

    def test_a_cancelled_order_brought_back_takes_its_stock_again(self):
        order = self.paid()
        set_status(order, Order.Status.CANCELLED, by=self.staff)
        set_status(order, Order.Status.PROCESSING, by=self.staff)
        self.assertEqual(stock_of(self.variant), 7)
        set_status(order, Order.Status.CANCELLED, by=self.staff)
        self.assertEqual(stock_of(self.variant), 10)

    def test_a_callback_replayed_after_staff_moved_the_order_changes_nothing(self):
        """The gateway may say "paid" again once the parcel is being packed.

        It must not take the stock a second time, put the order back to
        "paid", or tell the owner about a new order.
        """
        order = self.paid()
        set_status(order, Order.Status.PROCESSING, by=self.staff)
        with mock.patch.object(telegram, 'notify_paid_order') as told:
            services.apply_successful_payment(Order.objects.get(pk=order.pk))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(stock_of(self.variant), 7)
        told.assert_not_called()

    def test_a_payment_that_arrives_for_a_cancelled_order_still_counts(self):
        """The customer cancelled and then paid anyway: the money is real."""
        services.cancel_order(self.order)
        services.apply_successful_payment(Order.objects.get(pk=self.order.pk))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(stock_of(self.variant), 7)
