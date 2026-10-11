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
import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib import admin as django_admin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from cart.models import Cart, CartItem
from core import telegram
from core.ratelimit import RATE_LIMIT_MESSAGE
from panel.models import OrderStatusChange
from panel.services import set_status
from payment import promos, services, views
from payment.admin import OrderAdmin
from payment.models import DeliveryOption, Order, PromoCode

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
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


#: What a parcel costs to send in these tests, in so'm.
FEE = Decimal('15000')
Kind = PromoCode.Kind


def code(kind, value=0, name='KOD', products=(), **limits):
    """A promo code of ``kind``, switched on, with the limits given."""
    promo = PromoCode(code=name, kind=kind, value=value, **limits)
    promo.full_clean()
    promo.save()
    promo.products.set(products)
    return promo


def cart_of(user, *lines):
    """An open cart of ``lines``, each a ``(variant, quantity)`` pair."""
    cart = Cart.objects.create(user=user, status=True)
    for variant, quantity in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity,
                                price_stat=variant.price)
    return cart


def place(user, cart, promo=None, delivery=FEE):
    """Turn ``cart`` into an order the way the checkout does, with ``promo``."""
    return services.create_order_from_cart(
        user, cart, phone=user.phone, address='Amir Temur 1', notes='',
        payment_method=Order.PaymentMethod.CLICK, delivery=delivery, promo=promo)


class PromoCase(TestCase):
    """A customer, two products at two prices, and the helpers above."""

    def setUp(self):
        self.user = make_user('xaridor', '+998901220003')
        self.shirt, self.shirt_m = make_product('Koʻylak', price='150000')
        self.hoodie, self.hoodie_m = make_product('Xudi', price='250000')

    def order(self, promo, *lines, delivery=FEE, user=None):
        """Place an order of ``lines`` (one shirt if none) with ``promo``."""
        user = user or self.user
        cart = cart_of(user, *(lines or [(self.shirt_m, 1)]))
        return place(user, cart, promo, delivery)

    def assertRefused(self, reason, promo, *lines, delivery=FEE, user=None):
        """The order is refused for ``reason`` and nothing is written."""
        user = user or self.user
        before = Order.objects.count()
        cart = cart_of(user, *(lines or [(self.shirt_m, 1)]))
        with self.assertRaises(promos.Refused) as caught:
            place(user, cart, promo, delivery)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(Order.objects.count(), before)
        cart.refresh_from_db()
        self.assertTrue(cart.status, 'a refused code must leave the cart open')
        # Out of the way, so the next cart in the same test can be opened.
        cart.delete()
        return caught.exception


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

    def test_the_django_admin_moves_stock_the_same_way(self):
        """The admin saves a status through the same function the panel does."""
        order = self.paid()
        order.status = Order.Status.CANCELLED
        form = mock.Mock(changed_data=['status'])
        request = mock.Mock(user=self.staff)
        OrderAdmin(Order, django_admin.site).save_model(request, order, form, change=True)
        self.assertEqual(stock_of(self.variant), 10)
        self.assertEqual(OrderStatusChange.objects.get().note, 'Django admin')

    def test_two_markings_of_one_payment_take_the_stock_once(self):
        """A callback and a second one, each holding a copy read before the other wrote."""
        first = Order.objects.get(pk=self.order.pk)
        second = Order.objects.get(pk=self.order.pk)
        services.apply_successful_payment(first)
        services.apply_successful_payment(second)
        self.assertEqual(stock_of(self.variant), 7)

    def test_a_gateways_cancellation_ends_only_an_order_still_awaiting_payment(self):
        """Not one that is paid, and not one staff have moved on to packing.

        The second was the gap: it read as cancelled with its stock still
        taken, and putting it back took the stock a second time.
        """
        services.apply_cancelled_payment(Order.objects.get(pk=self.order.pk))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

        _, other = make_product('Boshqa', stock=10)
        for status in (Order.Status.PAID, Order.Status.PROCESSING,
                       Order.Status.ON_THE_WAY, Order.Status.DONE):
            with self.subTest(status=status):
                order = order_of(self.customer, (other, 1))
                services.apply_successful_payment(order)
                set_status(order, status, by=self.staff)
                services.apply_cancelled_payment(Order.objects.get(pk=order.pk))
                order.refresh_from_db()
                self.assertEqual(order.status, status)

    def test_a_customers_cancel_does_not_undo_a_payment_that_landed_first(self):
        """The cancel page was opened before the payment and pressed after it."""
        held = Order.objects.get(pk=self.order.pk)
        self.paid()
        self.assertFalse(services.cancel_order(held))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(stock_of(self.variant), 7)


# ---------------------------------------------------------- the five kinds

class KindTests(PromoCase):
    """What each kind takes off, worked out under the lock and frozen."""

    def test_an_order_without_a_code_is_as_it_always_was(self):
        order = self.order(None)
        self.assertEqual(order.total_price, 150000 + FEE)
        self.assertEqual((order.promo, order.promo_code, order.discount), (None, '', 0))

    def test_a_sum_off_one_product(self):
        promo = code(Kind.PRODUCT_SUM, 20000, products=[self.shirt])
        order = self.order(promo)
        self.assertEqual(order.discount, 20000)
        self.assertEqual(order.total_price, 150000 + FEE - 20000)
        self.assertEqual(order.discount_product, self.shirt)
        self.assertEqual((order.promo, order.promo_code), (promo, 'KOD'))

    def test_a_product_code_comes_off_one_piece_whatever_the_quantity(self):
        """Two of the same shirt: 20 000 off one of them, not 40 000."""
        promo = code(Kind.PRODUCT_SUM, 20000, products=[self.shirt])
        order = self.order(promo, (self.shirt_m, 2))
        self.assertEqual(order.discount, 20000)
        self.assertEqual(order.total_price, 300000 + FEE - 20000)

    def test_a_sum_is_never_more_than_the_item_costs(self):
        promo = code(Kind.PRODUCT_SUM, 400000, products=[self.shirt])
        order = self.order(promo, (self.shirt_m, 1), (self.hoodie_m, 1))
        self.assertEqual(order.discount, 150000)

    def test_a_share_off_one_product_is_rounded_down(self):
        _, odd = make_product('Toq narx', price='149999')
        promo = code(Kind.PRODUCT_PERCENT, 10, products=[odd.product])
        order = self.order(promo, (odd, 3))
        self.assertEqual(order.discount, 14999)

    def test_the_dearest_item_the_code_covers_is_the_one_discounted(self):
        promo = code(Kind.PRODUCT_PERCENT, 10, products=[self.shirt, self.hoodie])
        order = self.order(promo, (self.shirt_m, 2), (self.hoodie_m, 1))
        self.assertEqual(order.discount, 25000)
        self.assertEqual(order.discount_product, self.hoodie)

    def test_a_dearer_item_the_code_does_not_cover_is_left_alone(self):
        promo = code(Kind.PRODUCT_PERCENT, 10, products=[self.shirt])
        order = self.order(promo, (self.shirt_m, 1), (self.hoodie_m, 1))
        self.assertEqual(order.discount, 15000)
        self.assertEqual(order.discount_product, self.shirt)

    def test_a_cart_with_none_of_the_codes_products_is_refused_it(self):
        promo = code(Kind.PRODUCT_SUM, 20000, products=[self.hoodie])
        self.assertRefused(promos.NO_PRODUCT, promo, (self.shirt_m, 1))
        # The control: the same code on a cart that holds the product.
        self.assertEqual(self.order(promo, (self.hoodie_m, 1)).discount, 20000)

    def test_a_sum_off_the_order_comes_off_goods_and_delivery_together(self):
        order = self.order(code(Kind.ORDER_SUM, 30000))
        self.assertEqual(order.discount, 30000)
        self.assertEqual(order.total_price, 150000 + FEE - 30000)
        self.assertIsNone(order.discount_product)

    def test_a_share_off_the_order_is_a_share_of_goods_and_delivery(self):
        """Ten per cent of 165 000, not of the 150 000 of goods."""
        order = self.order(code(Kind.ORDER_PERCENT, 10))
        self.assertEqual(order.discount, 16500)
        self.assertEqual(order.total_price, 148500)

    def test_a_share_off_the_order_is_rounded_down(self):
        _, odd = make_product('Toq narx', price='149999')
        order = self.order(code(Kind.ORDER_PERCENT, 7), (odd, 1))
        # 7 % of 164 999 is 11 549.93.
        self.assertEqual(order.discount, 11549)

    def test_free_delivery_takes_off_the_fee_and_keeps_it_on_record(self):
        order = self.order(code(Kind.FREE_DELIVERY))
        self.assertEqual(order.discount, FEE)
        self.assertEqual(order.delivery_price, FEE)
        self.assertEqual(order.total_price, 150000)

    def test_free_delivery_on_an_order_that_ships_free_is_refused(self):
        promo = code(Kind.FREE_DELIVERY)
        self.assertRefused(promos.NOTHING_OFF, promo, delivery=Decimal('0'))
        self.assertEqual(self.order(promo).discount, FEE)

    def test_the_total_is_always_goods_plus_delivery_less_the_discount(self):
        kinds = [(Kind.PRODUCT_SUM, 20000), (Kind.PRODUCT_PERCENT, 15),
                 (Kind.ORDER_SUM, 30000), (Kind.ORDER_PERCENT, 15),
                 (Kind.FREE_DELIVERY, 0)]
        for index, (kind, value) in enumerate(kinds):
            with self.subTest(kind=kind):
                user = make_user('mijoz%d' % index, '+99890122001%d' % index)
                promo = code(kind, value, name='KOD%d' % index, products=[self.shirt])
                order = self.order(promo, (self.shirt_m, 2), (self.hoodie_m, 1), user=user)
                self.assertGreater(order.discount, 0)
                self.assertEqual(order.total_price, 550000 + FEE - order.discount)

    def test_a_code_never_makes_an_order_free(self):
        """A gateway cannot be asked for nothing: the floor is left to pay."""
        for kind, value in ((Kind.ORDER_SUM, 900000), (Kind.ORDER_PERCENT, 100)):
            with self.subTest(kind=kind):
                promo = code(kind, value, name='HAMMA%s' % value, once_per_customer=False)
                order = self.order(promo)
                self.assertEqual(order.total_price, promos.FLOOR)
                self.assertEqual(order.discount, 150000 + FEE - promos.FLOOR)

    def test_the_floor_holds_for_a_code_off_one_item_too(self):
        """All of a cheap item, with nothing to send it: the floor is still left."""
        _, cheap = make_product('Arzon', price='5000')
        promo = code(Kind.PRODUCT_PERCENT, 100, products=[cheap.product])
        order = self.order(promo, (cheap, 1), delivery=Decimal('0'))
        self.assertEqual((order.discount, order.total_price), (4000, promos.FLOOR))

    def test_an_order_already_at_the_floor_is_refused_every_kind(self):
        _, tiny = make_product('Mayda', price='800')
        for index, kind in enumerate((Kind.PRODUCT_SUM, Kind.ORDER_SUM, Kind.ORDER_PERCENT)):
            with self.subTest(kind=kind):
                promo = code(kind, 50, name='PAST%d' % index, products=[tiny.product])
                self.assertRefused(promos.NOTHING_OFF, promo, (tiny, 1), delivery=Decimal('0'))

    def test_between_two_items_at_one_price_the_first_in_the_cart_is_discounted(self):
        """Settled the same way every time, so the form and the lock agree."""
        twin, twin_m = make_product('Egizak', price='150000')
        promo = code(Kind.PRODUCT_SUM, 20000, products=[self.shirt, twin])
        order = self.order(promo, (twin_m, 1), (self.shirt_m, 1))
        self.assertEqual(order.discount_product, twin)

    def test_the_preview_gives_a_figure_for_each_delivery_fee(self):
        """And 0 for a fee the code takes nothing off, when another fee has something."""
        cart = cart_of(self.user, (self.shirt_m, 1))
        lines = list(cart.cart_items.select_related('variant__product'))
        free = code(Kind.FREE_DELIVERY)
        seen = promos.preview('KOD', self.user, lines,
                              {'post': Decimal('0'), 'door': Decimal('40000')})
        self.assertEqual(seen.discounts, {'post': 0, 'door': 40000})
        with self.assertRaises(promos.Refused) as caught:
            promos.preview('KOD', self.user, lines, {'post': Decimal('0')})
        self.assertEqual(caught.exception.reason, promos.NOTHING_OFF)
        self.assertEqual(free.used_count, 0)

    def test_a_code_changed_afterwards_does_not_rewrite_the_order(self):
        promo = code(Kind.ORDER_SUM, 30000)
        order = self.order(promo)
        PromoCode.objects.filter(pk=promo.pk).update(value=1, is_active=False)
        order.refresh_from_db()
        self.assertEqual((order.discount, order.total_price), (30000, 135000))

    def test_a_code_an_order_points_at_cannot_be_deleted(self):
        promo = code(Kind.ORDER_SUM, 30000)
        self.order(promo)
        with self.assertRaises(ProtectedError):
            promo.delete()


# ---------------------------------------------------------------- the limits

class LimitTests(PromoCase):
    """Each way a code is refused, beside the same order going through."""

    def test_a_code_switched_off_is_refused(self):
        promo = code(Kind.ORDER_SUM, 30000, is_active=False)
        self.assertRefused(promos.UNKNOWN, promo)
        PromoCode.objects.filter(pk=promo.pk).update(is_active=True)
        self.assertEqual(self.order(promo).discount, 30000)

    def test_a_code_is_refused_outside_its_dates(self):
        now = timezone.now()
        early = code(Kind.ORDER_SUM, 30000, name='ERTA', starts_at=now + timedelta(hours=1))
        late = code(Kind.ORDER_SUM, 30000, name='KECH', ends_at=now - timedelta(hours=1))
        self.assertRefused(promos.UNKNOWN, early)
        self.assertRefused(promos.UNKNOWN, late)
        inside = code(Kind.ORDER_SUM, 30000, name='AYNI',
                      starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=1))
        self.assertEqual(self.order(inside).discount, 30000)

    def test_a_code_that_is_used_up_is_refused(self):
        promo = code(Kind.ORDER_SUM, 30000, max_uses=2, used_count=2)
        self.assertRefused(promos.UNKNOWN, promo)
        PromoCode.objects.filter(pk=promo.pk).update(used_count=1)
        self.assertEqual(self.order(promo).discount, 30000)

    def test_the_minimum_is_set_against_the_goods_not_the_delivery(self):
        promo = code(Kind.ORDER_SUM, 30000, min_subtotal=160000)
        refusal = self.assertRefused(promos.MINIMUM, promo)       # 150 000 of goods
        self.assertIn('160\u00a0000', str(refusal.message))
        exact = code(Kind.ORDER_SUM, 30000, name='TENG', min_subtotal=150000)
        self.assertEqual(self.order(exact).discount, 30000)

    def test_once_per_customer_refuses_a_customer_who_paid_with_it(self):
        promo = code(Kind.ORDER_SUM, 30000)
        services.apply_successful_payment(self.order(promo))
        self.assertRefused(promos.USED, promo)
        # Another customer may still use it.
        other = make_user('boshqa', '+998901220004')
        self.assertEqual(self.order(promo, user=other).discount, 30000)

    def test_an_unpaid_order_with_the_code_holds_it_until_paid_or_cancelled(self):
        """Or several orders could be opened with it first and all paid after."""
        promo = code(Kind.ORDER_SUM, 30000)
        first = self.order(promo)
        self.assertRefused(promos.UNPAID, promo)
        services.cancel_order(first)
        self.assertEqual(self.order(promo).discount, 30000)

    def test_a_code_with_a_number_of_uses_is_held_by_an_unpaid_order_as_well(self):
        """Or one customer could open a dozen orders under its last use."""
        promo = code(Kind.ORDER_SUM, 30000, max_uses=1, once_per_customer=False)
        first = self.order(promo)
        self.assertRefused(promos.UNPAID, promo)
        # Paid, it is used up for everyone; a customer may still buy twice with
        # a code that has uses left.
        services.apply_successful_payment(first)
        self.assertRefused(promos.UNKNOWN, promo)
        many = code(Kind.ORDER_SUM, 30000, name='KOP', max_uses=5, once_per_customer=False)
        services.apply_successful_payment(self.order(many))
        self.assertEqual(self.order(many).discount, 30000)

    def test_a_code_for_any_number_of_uses_is_not_held_by_an_earlier_order(self):
        promo = code(Kind.ORDER_SUM, 30000, once_per_customer=False)
        services.apply_successful_payment(self.order(promo))
        self.order(promo)
        self.assertEqual(self.order(promo).discount, 30000)

    def test_a_code_switched_off_between_the_form_and_the_lock_is_refused(self):
        """The form held a row that was good when it read it."""
        held = code(Kind.ORDER_SUM, 30000)
        PromoCode.objects.filter(pk=held.pk).update(is_active=False)
        self.assertTrue(held.is_active, 'the copy the form holds still reads on')
        self.assertRefused(promos.UNKNOWN, held)

    def test_a_code_deleted_between_the_form_and_the_lock_is_refused(self):
        held = code(Kind.ORDER_SUM, 30000)
        PromoCode.objects.filter(pk=held.pk).delete()
        self.assertRefused(promos.UNKNOWN, held)

    def test_a_typed_code_is_found_whatever_its_case_or_spacing(self):
        promo = code(Kind.ORDER_SUM, 30000, name='YOZ2026')
        for typed in ('YOZ2026', 'yoz2026', '  Yoz 2026 '):
            with self.subTest(typed=typed):
                self.assertEqual(promos.find(typed), promo)
        for typed in ('', 'YOZ', 'YOZ2026!', 'ЁЗ2026', 'x' * 60):
            with self.subTest(typed=typed):
                self.assertIsNone(promos.find(typed))

    def test_four_refusals_read_the_same_so_codes_cannot_be_fished_for(self):
        """Not there, switched off, out of date and used up: one sentence."""
        cart = cart_of(self.user, (self.shirt_m, 1))
        lines = list(cart.cart_items.select_related('variant__product'))
        now = timezone.now()
        code(Kind.ORDER_SUM, 30000, name='OFF', is_active=False)
        code(Kind.ORDER_SUM, 30000, name='KECH', ends_at=now - timedelta(days=1))
        code(Kind.ORDER_SUM, 30000, name='TUGADI', max_uses=1, used_count=1)
        said = set()
        for typed in ('YOQ123', 'OFF', 'KECH', 'TUGADI'):
            with self.assertRaises(promos.Refused) as caught:
                promos.apply(typed, self.user, lines, FEE)
            self.assertEqual(caught.exception.reason, promos.UNKNOWN)
            said.add(str(caught.exception.message))
        self.assertEqual(len(said), 1)

    def test_a_code_is_spelt_in_latin_capitals_and_digits(self):
        for name in ('AB', 'A' * 25, 'YOZ-10', 'ЁЗ10', 'yoz 10!'):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                PromoCode(code=name, kind=Kind.ORDER_SUM, value=1000).full_clean()
        promo = PromoCode(code=' yoz 10 ', kind=Kind.ORDER_SUM, value=1000)
        promo.full_clean()
        promo.save()
        self.assertEqual(promo.code, 'YOZ10')

    def test_a_value_has_to_fit_its_kind(self):
        bad = [(Kind.ORDER_PERCENT, 0), (Kind.ORDER_PERCENT, 101),
               (Kind.PRODUCT_PERCENT, 150), (Kind.ORDER_SUM, 0), (Kind.PRODUCT_SUM, 0)]
        for index, (kind, value) in enumerate(bad):
            with self.subTest(kind=kind, value=value), self.assertRaises(ValidationError):
                PromoCode(code='KOD%d' % index, kind=kind, value=value).full_clean()
        free = PromoCode(code='BEPUL', kind=Kind.FREE_DELIVERY, value=5000)
        free.full_clean()
        self.assertEqual(free.value, 0)

    def test_a_code_cannot_end_before_it_starts(self):
        now = timezone.now()
        with self.assertRaises(ValidationError):
            PromoCode(code='TESKARI', kind=Kind.ORDER_SUM, value=1000,
                      starts_at=now, ends_at=now - timedelta(days=1)).full_clean()


# ------------------------------------------------------------------ the uses

class UseTests(PromoCase):
    """A use is counted when the order is paid, once, and comes back."""

    def setUp(self):
        super().setUp()
        self.staff = make_staff()
        self.promo = code(Kind.ORDER_SUM, 30000, max_uses=5)

    def uses(self):
        """How many uses the code has now."""
        self.promo.refresh_from_db()
        return self.promo.used_count

    def test_an_order_that_is_only_placed_holds_no_use(self):
        self.order(self.promo)
        self.assertEqual(self.uses(), 0)

    def test_paying_counts_one_use_and_a_replay_counts_no_more(self):
        order = self.order(self.promo)
        services.apply_successful_payment(order)
        services.apply_successful_payment(Order.objects.get(pk=order.pk))
        self.assertEqual(self.uses(), 1)

    def test_a_staff_cancellation_gives_the_use_back(self):
        order = self.order(self.promo)
        services.apply_successful_payment(order)
        set_status(Order.objects.get(pk=order.pk), Order.Status.CANCELLED, by=self.staff)
        self.assertEqual(self.uses(), 0)
        # And the customer may use the code again.
        self.assertEqual(self.order(self.promo).discount, 30000)

    def test_a_customer_cancelling_an_unpaid_order_changes_no_count(self):
        services.cancel_order(self.order(self.promo))
        self.assertEqual(self.uses(), 0)

    def test_staff_marking_an_order_paid_counts_the_use(self):
        set_status(self.order(self.promo), Order.Status.PAID, by=self.staff)
        self.assertEqual(self.uses(), 1)

    def test_an_order_without_a_code_counts_nothing(self):
        services.apply_successful_payment(self.order(None))
        self.assertEqual(self.uses(), 0)

    def test_the_count_never_goes_below_nothing(self):
        order = self.order(self.promo)
        services.apply_successful_payment(order)
        PromoCode.objects.filter(pk=self.promo.pk).update(used_count=0)
        set_status(Order.objects.get(pk=order.pk), Order.Status.CANCELLED, by=self.staff)
        self.assertEqual(self.uses(), 0)


# ---------------------------------------------------------------- the gateway

CLICK = {'CLICK': {'SERVICE_ID': '111', 'MERCHANT_ID': '222', 'SECRET_KEY': 'sir',
                   'ACCOUNT_MODEL': 'payment.models.Order', 'ACCOUNT_FIELD': 'id',
                   'ONE_TIME_PAYMENT': True, 'COMMISSION_PERCENT': 0.0}}


@override_settings(TOLOV=CLICK, CLICK_SERVICE_ID='111', CLICK_MERCHANT_ID='222')
class GatewayTests(PromoCase):
    """The gateway is asked for the discounted total and paid exactly that."""

    def click(self, order, amount, action, prepare_id=''):
        """Post one Click callback for ``order``, signed as Click signs it."""
        params = {'click_trans_id': '900%d' % order.pk, 'service_id': '111',
                  'merchant_trans_id': str(order.pk), 'amount': str(amount),
                  'action': str(action), 'error': '0', 'sign_time': '2026-10-11 12:00:00'}
        if prepare_id:
            params['merchant_prepare_id'] = str(prepare_id)
        signed = (params['click_trans_id'] + '111' + 'sir' + params['merchant_trans_id']
                  + str(prepare_id) + params['amount'] + params['action'] + params['sign_time'])
        params['sign_string'] = hashlib.md5(signed.encode()).hexdigest()
        return self.client.post(reverse('click_webhook'), params).json()

    def test_the_pay_link_asks_for_the_discounted_total(self):
        order = self.order(code(Kind.ORDER_PERCENT, 10))
        with mock.patch.object(services.ClickGateway, 'create_payment',
                               return_value='https://my.click.uz/pay') as asked:
            services.generate_paylink(order, 'https://graphix.uz/uz/order/1/')
        self.assertEqual(asked.call_args.kwargs['amount'], Decimal('148500'))

    def test_a_click_payment_of_the_discounted_total_is_accepted(self):
        promo = code(Kind.ORDER_PERCENT, 10)
        order = self.order(promo)
        prepared = self.click(order, 148500, action=0)
        self.assertEqual(prepared['error'], 0, prepared)
        done = self.click(order, 148500, action=1,
                          prepare_id=prepared['merchant_prepare_id'])
        self.assertEqual(done['error'], 0, done)
        order.refresh_from_db()
        promo.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(promo.used_count, 1)

    def test_a_cancelled_order_cannot_be_paid_for(self):
        """Click asks before it charges, and is told the order is not there.

        Without this a once-per-customer code had no limit: place an order
        with it, keep the pay page open, cancel the order, which frees the
        code, place another, and pay for them all.
        """
        promo = code(Kind.ORDER_PERCENT, 10)
        first = self.order(promo)
        services.cancel_order(first)
        second = self.order(promo)                      # the code is free again
        refused = self.click(first, 148500, action=0)
        self.assertEqual(refused['error'], -5, refused)
        first.refresh_from_db()
        self.assertEqual(first.status, Order.Status.CANCELLED)
        # The live order is paid for as usual, and the code was used once.
        prepared = self.click(second, 148500, action=0)
        self.click(second, 148500, action=1, prepare_id=prepared['merchant_prepare_id'])
        second.refresh_from_db()
        promo.refresh_from_db()
        self.assertEqual(second.status, Order.Status.PAID)
        self.assertEqual(promo.used_count, 1)

    def test_a_payment_already_under_way_when_the_order_is_cancelled_is_kept(self):
        """Click has charged the card by then, so the order is paid, not lost."""
        order = self.order(None)
        prepared = self.click(order, 165000, action=0)
        services.cancel_order(Order.objects.get(pk=order.pk))
        done = self.click(order, 165000, action=1, prepare_id=prepared['merchant_prepare_id'])
        self.assertEqual(done['error'], 0, done)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_payme_is_refused_a_cancelled_order_before_it_charges(self):
        from tolov.core.exceptions import AccountNotFound
        order = self.order(None)
        # The hook as tolov calls it, on a view that was not built from a
        # request: Payme has no credentials here to build one with.
        view = views.PaymeWebhookAPIView.__new__(views.PaymeWebhookAPIView)
        view.before_check_perform_transaction({}, order)          # a live order passes
        services.cancel_order(order)
        with self.assertRaises(AccountNotFound):
            view.before_check_perform_transaction({}, Order.objects.get(pk=order.pk))

    def test_a_click_payment_of_the_full_price_is_not(self):
        """The order costs what it was frozen at, and no other sum pays it."""
        order = self.order(code(Kind.ORDER_PERCENT, 10))
        refused = self.click(order, 165000, action=0)
        self.assertEqual(refused['error'], -2, refused)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAYING)


# --------------------------------------------------------------- the checkout

class CheckoutCase(PromoCase):
    """A signed-in customer with one shirt in the cart, at the checkout."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.geo = make_regions()
        self.client.force_login(self.user)
        self.cart = cart_of(self.user, (self.shirt_m, 1))
        self.office = DeliveryOption.objects.get(code='uzpost_office')
        self.door = DeliveryOption.objects.get(code='uzpost_door')

    def form(self, **over):
        """A checkout form that would place the order, with ``over`` on top."""
        data = {'name': 'Dilnoza Karimova', 'phone': '+998 90 122 00 03',
                'delivery_option': 'uzpost_office',
                'region': self.geo['tashkent'].pk, 'district': self.geo['chilonzor'].pk,
                'postal_index': '100011', 'payment_method': 'click', 'notes': ''}
        data.update(over)
        return {key: value for key, value in data.items() if value is not None}

    def post(self, **over):
        return self.client.post(reverse('checkout'), self.form(**over))

    def apply(self, typed, **over):
        """Press "Qoʻllash" with ``typed`` in the field."""
        return self.post(promo_code=typed, apply_promo='1', **over)

    def said(self, response):
        """Every message the page came back with, as text."""
        return [str(m) for m in response.context['messages']]


class CheckoutTests(CheckoutCase):
    """The field at the checkout, used the way a page without scripts uses it."""

    def test_the_field_is_in_the_form_above_the_order_button(self):
        """On a phone the summary comes after the button; the field must not."""
        html = self.client.get(reverse('checkout')).content.decode()
        form = html.split('data-checkout', 1)[1].split('</form>', 1)[0]
        self.assertIn('name="promo_code"', form)
        apply = form.index('name="apply_promo"')
        order_button = form.rindex('type="submit"')
        self.assertLess(apply, order_button)
        self.assertIn('formnovalidate', form[apply - 200:apply + 200])
        # Nothing is taken off and nothing says so until a code is tried.
        self.assertRegex(html, r'data-promo-row hidden')

    def test_enter_in_a_field_still_places_the_order(self):
        """A form's first submit button is the one Enter presses.

        "Qoʻllash" now comes before the order button, so the order button is
        in the form once more ahead of it, out of sight and out of the tab
        order, and carries no name: pressing it applies nothing.
        """
        html = self.client.get(reverse('checkout')).content.decode()
        form = html.split('data-checkout', 1)[1].split('</form>', 1)[0]
        first = form[form.index('<button'):].split('>', 1)[0]
        self.assertIn('type="submit"', first)
        self.assertIn('class="sr-only"', first)
        self.assertIn('tabindex="-1"', first)
        self.assertNotIn('name=', first)

    def test_applying_a_code_shows_the_discount_and_places_no_order(self):
        code(Kind.ORDER_PERCENT, 10)
        response = self.apply('kod', name='')          # the form is not finished
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        expected = (150000 + self.office.price) // 10
        self.assertEqual(response.context['discount'], expected)
        self.assertEqual(response.context['total'], 150000 + self.office.price - expected)
        html = response.content.decode()
        self.assertNotRegex(html, r'data-promo-row hidden')
        self.assertIn('Chegirma: 16\u00a0500 soʻm. Jami: 148\u00a0500 soʻm.', html)
        # Not a word about the empty name: the customer asked about the code.
        self.assertEqual(self.said(response), [])

    def test_what_was_typed_comes_back_with_the_code(self):
        code(Kind.ORDER_SUM, 30000)
        html = self.apply('kod', notes='Qoʻngʻiroq qiling').content.decode()
        self.assertIn('value="Dilnoza Karimova"', html)
        self.assertIn('Qoʻngʻiroq qiling', html)
        self.assertIn('value="100011"', html)

    def test_a_refused_code_comes_back_as_typed_with_the_reason(self):
        response = self.apply('yoq 123')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(response.context['discount'], 0)
        self.assertEqual(self.said(response), [str(promos.MESSAGES[promos.UNKNOWN])])
        html = response.content.decode()
        self.assertIn('value="yoq 123"', html)
        self.assertRegex(html, r'data-promo-row hidden')
        self.assertIn('promo__status--refused', html)

    def test_applying_an_empty_field_asks_for_a_code(self):
        response = self.apply('')
        self.assertEqual(self.said(response), ['Promokodni kiriting.'])

    def test_a_product_code_names_the_product_it_came_off(self):
        code(Kind.PRODUCT_SUM, 20000, products=[self.shirt])
        html = self.apply('KOD').content.decode()
        self.assertIn('Chegirma (Koʻylak): 20\u00a0000 soʻm.', html)

    def test_the_discount_follows_the_delivery_method(self):
        """A share of the order is a share of whichever fee is chosen."""
        code(Kind.ORDER_PERCENT, 10)
        by_method = {}
        for option in (self.office, self.door):
            response = self.apply('KOD', delivery_option=option.code, postal_index=None,
                                  address='Amir Temur 1')
            by_method[option.code] = response.context['discount']
            self.assertEqual(response.context['discount'], (150000 + option.price) // 10)
        self.assertNotEqual(by_method['uzpost_office'], by_method['uzpost_door'])
        # The page's script is handed both figures, so it need not ask again.
        self.assertEqual(response.context['promo'].discounts, by_method)
        self.assertIn('&quot;uzpost_door&quot;: %d' % by_method['uzpost_door'],
                      response.content.decode())

    def test_free_delivery_takes_off_the_fee_of_the_method_chosen(self):
        code(Kind.FREE_DELIVERY)
        response = self.apply('KOD', delivery_option='uzpost_door', postal_index=None,
                              address='Amir Temur 1')
        self.assertEqual(response.context['discount'], self.door.price)
        self.assertEqual(response.context['total'], 150000)

    def test_an_order_placed_with_a_typed_code_uses_it(self):
        """Whether or not "Qoʻllash" was pressed first."""
        promo = code(Kind.ORDER_SUM, 30000)
        response = self.post(promo_code='kod')
        order = Order.objects.get()
        self.assertRedirects(response, reverse('payment', args=[order.pk]))
        self.assertEqual((order.promo, order.discount), (promo, 30000))
        self.assertEqual(order.total_price, 150000 + self.office.price - 30000)

    def test_a_refused_code_stops_the_order_and_says_why(self):
        response = self.post(promo_code='YOQ123')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.said(response), [str(promos.MESSAGES[promos.UNKNOWN])])
        # The control: the same form with a code that is good.
        code(Kind.ORDER_SUM, 30000)
        self.post(promo_code='KOD')
        self.assertEqual(Order.objects.get().discount, 30000)

    def test_an_order_without_a_code_is_placed_as_before(self):
        self.post()
        order = Order.objects.get()
        self.assertEqual((order.promo, order.discount), (None, 0))
        self.assertEqual(order.total_price, 150000 + self.office.price)

    def test_a_code_refused_under_the_lock_brings_the_checkout_back(self):
        """Good at the form, switched off before the order was written."""
        code(Kind.ORDER_SUM, 30000)
        with mock.patch.object(services, 'create_order_from_cart',
                               side_effect=promos.Refused(promos.UNKNOWN)):
            response = self.post(promo_code='KOD')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(response.context['discount'], 0)
        self.assertEqual(self.said(response), [str(promos.MESSAGES[promos.UNKNOWN])])

    def test_taking_the_code_out_empties_the_field(self):
        code(Kind.ORDER_SUM, 30000)
        response = self.post(promo_code='KOD', remove_promo='1')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(response.context['discount'], 0)
        self.assertIn('name="promo_code" id="id_promo_code"', response.content.decode())
        self.assertNotIn('value="KOD"', response.content.decode())


class WithoutScriptsTests(CheckoutCase):
    """The checkout completes with scripts off, with a code and without one.

    It could not: the district list was filled by a script and by nothing
    else, so the select held one placeholder and no order could be placed.
    """

    def districts(self, html):
        """The district select as shipped: ``[(heading, [(value, selected)])]``."""
        select = re.search(r'<select[^>]*name="district".*?</select>', html, re.S).group(0)
        groups = re.findall(r'<optgroup label="([^"]*)">(.*?)</optgroup>', select, re.S)
        return [(label, re.findall(r'<option value="(\d+)" ?(selected)?', body))
                for label, body in groups]

    def test_the_page_ships_every_district_under_its_region(self):
        html = self.client.get(reverse('checkout')).content.decode()
        shipped = {label: [int(value) for value, _ in rows]
                   for label, rows in self.districts(html)}
        self.assertEqual(shipped, {
            'Toshkent shahri': [self.geo['chilonzor'].pk],
            'Samarqand viloyati': [self.geo['sam_city'].pk],
            'Boshqa': [self.geo['other_district'].pk]})

    def test_a_form_sent_back_keeps_its_district(self):
        """Under the chosen region's own headings, with the choice still made."""
        html = self.post(name='').content.decode()
        self.assertEqual(self.districts(html),
                         [('Tumanlar', [(str(self.geo['chilonzor'].pk), 'selected')])])

    def test_an_order_is_placed_from_what_the_page_ships_alone(self):
        """A region and a district read off the page, and nothing a script adds."""
        html = self.client.get(reverse('checkout')).content.decode()
        region = re.search(r'<option value="(\d+)"[^>]*>\s*Toshkent shahri', html).group(1)
        district = dict(self.districts(html))['Toshkent shahri'][0][0]
        for typed in ('', 'KOD'):
            with self.subTest(code=typed):
                Order.objects.all().delete()
                Cart.objects.filter(user=self.user).delete()
                cart_of(self.user, (self.shirt_m, 1))
                PromoCode.objects.all().delete()
                code(Kind.ORDER_SUM, 30000)
                response = self.post(region=region, district=district, promo_code=typed)
                order = Order.objects.get()
                self.assertRedirects(response, reverse('payment', args=[order.pk]))
                self.assertEqual(order.discount, 30000 if typed else 0)

    def test_a_district_from_another_region_is_still_refused(self):
        """Every district is on offer now, so the server's own check matters."""
        response = self.post(district=self.geo['sam_city'].pk)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.said(response), ['Tanlangan tuman bu viloyatga tegishli emas.'])


class CheckoutScriptTests(CheckoutCase):
    """The same answer as JSON, for the page's script."""

    def ask(self, typed):
        return self.client.post(reverse('checkout_promo'), {'promo_code': typed})

    def test_a_good_code_answers_with_a_figure_for_each_delivery_method(self):
        code(Kind.ORDER_PERCENT, 10)
        reply = self.ask(' kod ').json()
        self.assertEqual(reply, {
            'ok': True, 'code': 'KOD', 'product': '',
            'discounts': {'uzpost_office': (150000 + int(self.office.price)) // 10,
                          'uzpost_door': (150000 + int(self.door.price)) // 10}})

    def test_a_product_code_answers_with_the_product_in_the_readers_language(self):
        self.shirt.name_ru = 'Рубашка'
        self.shirt.save(update_fields=['name_ru'])
        code(Kind.PRODUCT_SUM, 20000, products=[self.shirt])
        reply = self.client.post('/ru/checkout/promo/', {'promo_code': 'KOD'}).json()
        self.assertEqual(reply['product'], 'Рубашка')

    def test_a_refused_code_answers_with_the_reason(self):
        reply = self.ask('YOQ123').json()
        self.assertEqual(reply, {'ok': False, 'error': str(promos.MESSAGES[promos.UNKNOWN])})

    def test_it_places_no_order_and_changes_no_cart(self):
        code(Kind.ORDER_SUM, 30000)
        self.ask('KOD')
        self.assertFalse(Order.objects.exists())
        self.cart.refresh_from_db()
        self.assertTrue(self.cart.status)

    def test_it_is_for_a_signed_in_customer_and_a_post(self):
        self.assertEqual(self.client.get(reverse('checkout_promo')).status_code, 405)
        self.client.logout()
        response = self.ask('KOD')
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_an_empty_cart_and_an_empty_field_are_answered_in_words(self):
        self.assertFalse(self.ask('').json()['ok'])
        self.cart.cart_items.all().delete()
        self.assertFalse(self.ask('KOD').json()['ok'])


class GuessingTests(CheckoutCase):
    """A code is short and worth money, so trying them is limited."""

    def ask(self, typed):
        return self.client.post(reverse('checkout_promo'), {'promo_code': typed}).json()

    def test_a_customer_gets_ten_tries_in_ten_minutes(self):
        code(Kind.ORDER_SUM, 30000)
        for attempt in range(views.PROMO_TRIES):
            self.assertEqual(self.ask('YOQ%03d' % attempt)['error'],
                             str(promos.MESSAGES[promos.UNKNOWN]))
        # The eleventh is refused whatever it is, a good code included.
        self.assertEqual(self.ask('KOD'), {'ok': False, 'error': str(RATE_LIMIT_MESSAGE)})

    def test_the_form_counts_the_same_tries(self):
        """Pressing "Qoʻllash" and placing an order are tries too."""
        code(Kind.ORDER_SUM, 30000)
        for attempt in range(views.PROMO_TRIES):
            self.apply('YOQ%03d' % attempt)
        response = self.post(promo_code='KOD')
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.said(response), [str(RATE_LIMIT_MESSAGE)])
        # Without a code the order is not held up by the limit.
        self.post()
        self.assertTrue(Order.objects.exists())

    def test_a_code_already_accepted_is_not_a_try_again(self):
        """The form is posted for every field corrected, and none is a guess."""
        code(Kind.ORDER_SUM, 30000)
        for _ in range(views.PROMO_TRIES + 5):
            response = self.apply('KOD', name='')
            self.assertEqual(response.context['discount'], 30000)
        self.post(promo_code='KOD')
        self.assertEqual(Order.objects.get().discount, 30000)

    def test_an_address_is_limited_across_customers(self):
        code(Kind.ORDER_SUM, 30000)
        with mock.patch.object(views, 'PROMO_TRIES_ADDRESS', 3):
            for index in range(3):
                other = make_user('mehmon%d' % index, '+99890122005%d' % index)
                cart_of(other, (self.shirt_m, 1))
                self.client.force_login(other)
                self.assertEqual(self.ask('YOQ%03d' % index)['error'],
                                 str(promos.MESSAGES[promos.UNKNOWN]))
            self.client.force_login(self.user)
            self.assertEqual(self.ask('KOD')['error'], str(RATE_LIMIT_MESSAGE))


# ------------------------------------------------- wherever a total is shown

class ShownTests(CheckoutCase):
    """The discount is on every page that shows the order's total."""

    def setUp(self):
        super().setUp()
        self.staff = make_staff()
        self.staff.is_superuser = True
        self.staff.save(update_fields=['is_superuser'])
        self.promo = code(Kind.PRODUCT_SUM, 20000, products=[self.shirt])
        self.post(promo_code='KOD')
        self.order = Order.objects.get()
        # A second order, placed without a code: the control for every page.
        self.other = make_user('boshqa', '+998901220004')
        self.plain = place(self.other, cart_of(self.other, (self.shirt_m, 1)))

    def test_the_payment_page(self):
        html = self.client.get(reverse('payment', args=[self.order.pk])).content.decode()
        self.assertIn('Promokod KOD: −20\u00a0000 soʻm', html)
        self.assertIn('%s soʻm' % '145\u00a0000', html)
        self.client.force_login(self.other)
        html = self.client.get(reverse('payment', args=[self.plain.pk])).content.decode()
        self.assertNotIn('Promokod', html)

    def test_the_customers_order_page_names_the_code_and_the_item(self):
        html = self.client.get(reverse('order_detail', args=[self.order.pk])).content.decode()
        self.assertIn('−20\u00a0000 soʻm', html)
        self.assertRegex(html, r'Promokod <span class="num">KOD</span>'
                               r'<span class="spec__sub">Koʻylak</span>')
        self.client.force_login(self.other)
        html = self.client.get(reverse('order_detail', args=[self.plain.pk])).content.decode()
        self.assertNotIn('Promokod', html)

    def test_the_panels_order_screen(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse('panel_order',
                                       kwargs={'order_no': self.order.order_no})).content.decode()
        self.assertIn('Promokod KOD', html)
        self.assertIn('−20\u00a0000 soʻm', html)
        self.assertIn('Koʻylak</span>', html)
        html = self.client.get(reverse('panel_order',
                                       kwargs={'order_no': self.plain.order_no})).content.decode()
        self.assertNotIn('Promokod KOD', html)

    def test_the_django_admin(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse('admin:payment_order_change',
                                       args=[self.order.pk])).content.decode()
        self.assertIn('KOD', html)
        self.assertIn('20000', html)
        self.assertEqual(self.client.get(reverse('admin:payment_promocode_changelist'))
                         .status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:payment_promocode_change',
                                                 args=[self.promo.pk])).status_code, 200)

    def test_the_telegram_message_for_a_paid_order(self):
        with mock.patch.object(telegram, 'notify') as sent:
            telegram.notify_paid_order(self.order)
        text, data = sent.call_args.args[0], sent.call_args.kwargs['data']['order']
        self.assertIn('<b>Jami:</b> 145000 soʻm', text)
        self.assertIn('<b>Promokod:</b> KOD — −20000 soʻm', text)
        self.assertEqual((data['total'], data['discount'], data['promo_code']),
                         (145000, 20000, 'KOD'))
        with mock.patch.object(telegram, 'notify') as sent:
            telegram.notify_paid_order(self.plain)
        text, data = sent.call_args.args[0], sent.call_args.kwargs['data']['order']
        self.assertNotIn('Promokod', text)
        self.assertEqual((data['discount'], data['promo_code']), (0, ''))

    def test_the_account_and_the_dashboard_count_what_was_paid(self):
        """Both read ``total_price``, which is already less the discount."""
        services.apply_successful_payment(self.order)
        self.client.force_login(self.staff)
        response = self.client.get(reverse('panel_dashboard'))
        self.assertEqual(response.context['revenue_today'], self.order.total_price)
        self.assertEqual(self.order.total_price, 150000 + self.office.price - 20000)


# ------------------------------------------------------------------ the panel

class PanelTests(PromoCase):
    """The owner makes, limits and switches off a code himself."""

    def setUp(self):
        super().setUp()
        self.staff = make_staff()
        self.client.force_login(self.staff)

    def form(self, **over):
        """What the new-code form posts for a sum off the order, plus ``over``."""
        data = {'code': 'YOZ10', 'kind': Kind.ORDER_SUM, 'value': '30000',
                'once_per_customer': 'on', 'is_active': 'on',
                'starts_on': '', 'ends_on': '', 'max_uses': '', 'min_subtotal': '',
                'note': ''}
        data.update(over)
        return {key: value for key, value in data.items() if value is not None}

    def make(self, **over):
        return self.client.post(reverse('panel_promo_new'), self.form(**over))

    def errors(self, response):
        """The form's refusals, by field."""
        return {name: [str(e) for e in errs]
                for name, errs in response.context['form'].errors.items()}

    def test_only_staff_reach_it(self):
        promo = code(Kind.ORDER_SUM, 30000)
        urls = [reverse('panel_promos'), reverse('panel_promo_new'),
                reverse('panel_promo', kwargs={'pk': promo.pk})]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.force_login(self.user)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)
            self.assertEqual(self.client.post(url, self.form()).status_code, 403, url)
        self.assertFalse(PromoCode.objects.filter(code='YOZ10').exists())

    def test_a_code_of_each_kind_can_be_made(self):
        made = [
            ('MAHSUM', Kind.PRODUCT_SUM, '20000', [self.shirt.pk]),
            ('MAHFOIZ', Kind.PRODUCT_PERCENT, '15', [self.shirt.pk, self.hoodie.pk]),
            ('BUYSUM', Kind.ORDER_SUM, '30000', None),
            ('BUYFOIZ', Kind.ORDER_PERCENT, '10', None),
            ('BEPUL', Kind.FREE_DELIVERY, '', None),
        ]
        for name, kind, value, products in made:
            with self.subTest(kind=kind):
                response = self.make(code=name, kind=kind, value=value, products=products)
                self.assertRedirects(response, reverse('panel_promos'))
                promo = PromoCode.objects.get(code=name)
                self.assertEqual(promo.kind, kind)
                self.assertEqual(promo.value, Decimal(value or 0))
                self.assertEqual(set(promo.products.values_list('pk', flat=True)),
                                 set(products or []))
                self.assertTrue(promo.is_active)
                self.assertTrue(promo.once_per_customer)
        # And each one works at the checkout's own rules.
        order = self.order(PromoCode.objects.get(code='MAHSUM'))
        self.assertEqual(order.discount, 20000)

    def test_a_code_is_kept_in_capitals_however_it_is_typed(self):
        self.make(code=' yoz 10 ')
        self.assertTrue(PromoCode.objects.filter(code='YOZ10').exists())

    def test_a_code_that_already_exists_is_refused_whatever_its_case(self):
        code(Kind.ORDER_SUM, 30000, name='YOZ10')
        response = self.make(code='yoz10')
        self.assertEqual(self.errors(response)['code'], ['Bunday promokod allaqachon bor.'])
        self.assertEqual(PromoCode.objects.count(), 1)

    def test_what_does_not_fit_is_refused_in_the_panels_words(self):
        refused = [
            ({'code': 'YOZ-10'}, 'code'),
            ({'code': 'AB'}, 'code'),
            ({'code': ''}, 'code'),
            ({'value': ''}, 'value'),
            ({'value': '0'}, 'value'),
            ({'kind': Kind.ORDER_PERCENT, 'value': '101'}, 'value'),
            ({'kind': Kind.PRODUCT_SUM, 'value': '20000'}, 'products'),
            ({'kind': 'chegirma'}, 'kind'),
            ({'max_uses': '-1'}, 'max_uses'),
            ({'starts_on': 'ertaga'}, 'starts_on'),
            ({'starts_on': '20/10/2026', 'ends_on': '19/10/2026'}, 'ends_on'),
        ]
        for over, field in refused:
            with self.subTest(over=over):
                response = self.make(**over)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, self.errors(response))
                self.assertFalse(PromoCode.objects.exists())
                # What was typed is still in the form.
                self.assertContains(response, 'name="note"')

    def test_a_refused_form_keeps_what_was_typed(self):
        response = self.make(code='YOZ-10', note='Instagram uchun', max_uses='50',
                             kind=Kind.PRODUCT_SUM, products=[self.hoodie.pk])
        html = response.content.decode()
        self.assertIn('value="YOZ-10"', html)
        self.assertIn('value="Instagram uchun"', html)
        self.assertIn('value="50"', html)
        self.assertRegex(html, r'value="%d"\s+checked' % self.hoodie.pk)
        self.assertNotRegex(html, r'value="%d"\s+checked' % self.shirt.pk)

    def test_products_are_kept_only_for_a_code_that_discounts_one_item(self):
        self.make(kind=Kind.ORDER_SUM, products=[self.shirt.pk])
        self.assertEqual(PromoCode.objects.get().products.count(), 0)

    def test_days_are_typed_day_first_and_cover_the_whole_of_each_day(self):
        self.make(starts_on='12/10/2026', ends_on='31/10/2026')
        promo = PromoCode.objects.get()
        zone = timezone.get_current_timezone()
        at = lambda *parts: timezone.make_aware(datetime(*parts), zone)
        self.assertEqual(promo.starts_at, at(2026, 10, 12))
        self.assertEqual(promos.standing(promo, at(2026, 10, 11, 23, 59)), promos.EARLY)
        self.assertEqual(promos.standing(promo, at(2026, 10, 12, 0, 1)), promos.LIVE)
        # Good until the last minute of its last day, in the shop's own time.
        self.assertEqual(promos.standing(promo, at(2026, 10, 31, 23, 59)), promos.LIVE)
        self.assertEqual(promos.standing(promo, at(2026, 11, 1, 0, 1)), promos.ENDED)
        html = self.client.get(reverse('panel_promo', kwargs={'pk': promo.pk})).content.decode()
        self.assertIn('value="12/10/2026"', html)
        self.assertIn('value="31/10/2026"', html)

    def test_the_limits_can_be_edited_and_the_spelling_and_kind_cannot(self):
        promo = code(Kind.ORDER_SUM, 30000, name='YOZ10')
        url = reverse('panel_promo', kwargs={'pk': promo.pk})
        response = self.client.post(url, self.form(
            code='BOSHQA', kind=Kind.FREE_DELIVERY, value='45000', max_uses='7',
            min_subtotal='200000', once_per_customer=None, is_active=None,
            ends_on='31/12/2026', note='Yangi yil'))
        self.assertRedirects(response, reverse('panel_promos'))
        promo.refresh_from_db()
        self.assertEqual((promo.code, promo.kind), ('YOZ10', Kind.ORDER_SUM))
        self.assertEqual((promo.value, promo.max_uses, promo.min_subtotal),
                         (45000, 7, 200000))
        self.assertFalse(promo.once_per_customer)
        self.assertFalse(promo.is_active)
        self.assertEqual(promo.note, 'Yangi yil')
        self.assertIsNotNone(promo.ends_at)

    def test_editing_a_code_does_not_touch_an_order_placed_with_it(self):
        promo = code(Kind.ORDER_SUM, 30000, name='YOZ10')
        order = self.order(promo)
        self.client.post(reverse('panel_promo', kwargs={'pk': promo.pk}),
                         self.form(value='90000'))
        order.refresh_from_db()
        self.assertEqual((order.discount, order.total_price), (30000, 150000 + FEE - 30000))

    def test_clearing_a_day_takes_the_limit_off(self):
        promo = code(Kind.ORDER_SUM, 30000, name='YOZ10',
                     ends_at=timezone.now() - timedelta(days=1))
        self.client.post(reverse('panel_promo', kwargs={'pk': promo.pk}), self.form())
        promo.refresh_from_db()
        self.assertIsNone(promo.ends_at)
        self.assertEqual(promos.standing(promo), promos.LIVE)

    def test_the_switch_on_the_list_turns_a_code_off_and_on(self):
        promo = code(Kind.ORDER_SUM, 30000)
        url = reverse('panel_reference_inline', kwargs={'kind': 'promo', 'pk': promo.pk})
        self.assertTrue(self.client.post(url, {'field': 'is_active', 'value': '0'}).json()['ok'])
        promo.refresh_from_db()
        self.assertFalse(promo.is_active)
        self.assertRefused(promos.UNKNOWN, promo)
        self.client.post(url, {'field': 'is_active', 'value': '1'})
        self.assertEqual(self.order(promo).discount, 30000)

    def test_the_switch_reaches_nothing_but_the_switch(self):
        """A value or a count changed one field at a time would skip the form's checks."""
        promo = code(Kind.ORDER_SUM, 30000, max_uses=5)
        url = reverse('panel_reference_inline', kwargs={'kind': 'promo', 'pk': promo.pk})
        for field, value in (('value', '1'), ('used_count', '0'), ('code', 'OGRI'),
                             ('max_uses', '999'), ('kind', Kind.ORDER_PERCENT)):
            with self.subTest(field=field):
                self.assertEqual(self.client.post(url, {'field': field, 'value': value})
                                 .status_code, 400)
        promo.refresh_from_db()
        self.assertEqual((promo.value, promo.code, promo.max_uses), (30000, 'KOD', 5))

    def test_a_code_nobody_used_can_be_deleted(self):
        promo = code(Kind.ORDER_SUM, 30000)
        url = reverse('panel_reference_delete', kwargs={'kind': 'promo', 'pk': promo.pk})
        self.assertEqual(self.client.post(url).json(), {'ok': True, 'name': 'KOD'})
        self.assertFalse(PromoCode.objects.exists())

    def test_a_code_an_order_was_placed_with_can_only_be_switched_off(self):
        promo = code(Kind.ORDER_SUM, 30000)
        self.order(promo)
        url = reverse('panel_reference_delete', kwargs={'kind': 'promo', 'pk': promo.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Yoqilgan', response.json()['error'])
        self.assertTrue(PromoCode.objects.filter(pk=promo.pk).exists())

    def test_the_list_says_what_each_code_is_and_where_it_stands(self):
        now = timezone.now()
        code(Kind.PRODUCT_SUM, 20000, name='MAHSUM', products=[self.shirt, self.hoodie],
             max_uses=5, used_count=2, note='Instagram')
        code(Kind.ORDER_PERCENT, 10, name='ERTA', starts_at=now + timedelta(days=2))
        code(Kind.ORDER_SUM, 30000, name='KECH', ends_at=now - timedelta(days=2))
        code(Kind.FREE_DELIVERY, name='TUGADI', max_uses=1, used_count=1)
        html = self.client.get(reverse('panel_promos')).content.decode()
        for name in ('MAHSUM', 'ERTA', 'KECH', 'TUGADI'):
            self.assertIn(name, html)
        self.assertIn('2 / 5', html)
        self.assertIn('Koʻylak, Xudi', html)
        self.assertIn('Instagram', html)
        self.assertIn('20\u00a0000 soʻm', html)
        self.assertIn('10 %', html)
        for badge in ('Hali boshlanmagan', 'Muddati tugagan', 'Limit tugagan'):
            self.assertEqual(html.count(badge), 1, badge)

    def test_the_panel_has_a_tab_for_it(self):
        html = self.client.get(reverse('panel_dashboard')).content.decode()
        self.assertIn('href="%s"' % reverse('panel_promos'), html)


# ------------------------------------------------------------ three languages

class LanguageTests(CheckoutCase):
    """Every sentence the phase added is written in all three languages."""

    SAID = {'uz': 'Chegirma: 16\u00a0500 soʻm. Jami: 148\u00a0500 soʻm.',
            'ru': 'Скидка: 16\u00a0500 сум. Итого: 148\u00a0500 сум.',
            'en': 'Discount: 16\u00a0500 soʻm. Total: 148\u00a0500 soʻm.'}
    REFUSED = {'uz': 'Bunday promokod yoʻq yoki u hozir amal qilmaydi.',
               'ru': 'Такого промокода нет, или он сейчас не действует.',
               'en': 'There is no such promo code, or it is not valid right now.'}

    def test_the_checkout_says_what_a_code_took_off(self):
        code(Kind.ORDER_PERCENT, 10, once_per_customer=False)
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                html = self.client.post('/%s/checkout/' % lang, self.form(
                    promo_code='KOD', apply_promo='1')).content.decode()
                self.assertIn(self.SAID[lang], html)
                # The script is handed the same sentence, to fill in itself.
                template = self.SAID[lang].replace('16\u00a0500', '{discount}') \
                                          .replace('148\u00a0500', '{total}')
                self.assertIn('data-said="%s"' % template, html)

    def test_a_refusal_is_in_the_readers_language(self):
        for lang in ('uz', 'ru', 'en'):
            with self.subTest(lang=lang):
                reply = self.client.post('/%s/checkout/promo/' % lang,
                                         {'promo_code': 'YOQ%s' % lang.upper()}).json()
                self.assertEqual(reply['error'], self.REFUSED[lang])

    def test_no_new_sentence_falls_back_to_uzbek(self):
        """The rules' own refusals and the kinds, read in each language."""
        seen = {}
        for lang in ('uz', 'ru', 'en'):
            with translation.override(lang):
                seen[lang] = ([str(text) for text in promos.MESSAGES.values()]
                              + [str(label) for label in Kind.labels])
        self.assertEqual(len(set(seen['uz']) & set(seen['ru'])), 0)
        self.assertEqual(len(set(seen['uz']) & set(seen['en'])), 0)

    def test_the_panel_reads_in_russian_and_english_too(self):
        self.client.force_login(make_staff())
        for lang, title in (('ru', 'Промокоды'), ('en', 'Promo codes')):
            with self.subTest(lang=lang):
                html = self.client.get('/%s/boshqaruv/promokodlar/' % lang).content.decode()
                self.assertIn(title, html)

    def test_the_terms_state_the_rules_in_each_language(self):
        """One code an order, not money, may be withdrawn, refunds what was paid."""
        words = {'uz': ('Bitta buyurtmada bitta promokod', 'Promokod pul emas',
                        'amalda toʻlangan summa'),
                 'ru': ('В одном заказе можно использовать один промокод',
                        'не деньги', 'фактически уплаченная сумма'),
                 'en': ('One promo code can be used per order',
                        'A promo code is not money', 'the amount actually paid')}
        for lang, phrases in words.items():
            with self.subTest(lang=lang):
                html = self.client.get('/%s/terms/' % lang).content.decode()
                for phrase in phrases:
                    self.assertIn(phrase, html)
                # The floor is the rule's own figure, not one typed into the page.
                self.assertIn('1\u00a0000', html.split('id="promo"')[1].split('</section>')[0])
