"""A cart that has been ordered can no longer be written to.

The checkout locks the cart's row, sums its lines and writes the order. The
cart's own views wrote lines without taking that lock, so a change sent at
the same moment as the order could land after the lines were summed: nine
shirts on an order charged for one. Sixty real pairs of requests produced
ten such orders.

The views now take the cart's lock before they write, and write only if the
cart is still open. These tests stand at the one moment that matters: the
view has found the cart, and the order is written before the view's own
write. Each also has its ordinary case beside it, where no order intervenes.
"""
from decimal import Decimal
from unittest import mock, skipUnless

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cart import services
from cart.models import Cart, CartItem
from payment import services as payment_services
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user


class OrderedCartTests(TestCase):
    """What the cart's three writes do with a cart ordered a moment before."""

    def setUp(self):
        self.user = make_user('xaridor', '+998901230001')
        self.product, self.variant = make_product('Koʻylak', stock=20)
        self.other, self.other_variant = make_product('Xudi', stock=20, price='250000')
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        self.line = CartItem.objects.create(cart=self.cart, variant=self.variant,
                                            quantity=1, price_stat=self.variant.price)

    def order_now(self):
        """Place the order, as the checkout does. Returns it."""
        return payment_services.create_order_from_cart(
            self.user, self.cart, phone=self.user.phone, address='Amir Temur 1',
            notes='', payment_method=Order.PaymentMethod.CLICK,
            delivery=Decimal('15000'))

    def ordered_under(self, name):
        """Patch the cart lookup ``name`` to answer, then write the order.

        The view is handed the cart as it was when it looked, still open, and
        by the time it writes the order exists: the losing side of the race.
        """
        stale = Cart.objects.get(pk=self.cart.pk)

        def found_then_ordered(request):
            if not Order.objects.filter(cart=self.cart).exists():
                self.order = self.order_now()
            return stale

        return mock.patch.object(services, name, side_effect=found_then_ordered)

    def lines(self):
        """What the ordered cart holds now: ``[(product, quantity)]``."""
        return sorted((item.variant.product.name, item.quantity)
                      for item in CartItem.objects.filter(cart=self.cart))

    def test_a_quantity_changed_as_the_order_is_placed_does_not_reach_it(self):
        with self.ordered_under('find_cart'):
            response = self.client.post(reverse('cart_update', args=[self.line.pk]),
                                        {'quantity': '9'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.lines(), [('Koʻylak', 1)])
        self.assertEqual(self.order.total_price, 150000 + 15000)

    def test_a_line_removed_as_the_order_is_placed_stays_on_it(self):
        with self.ordered_under('find_cart'):
            response = self.client.post(reverse('cart_remove', args=[self.line.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.lines(), [('Koʻylak', 1)])

    def test_a_product_added_as_the_order_is_placed_starts_the_next_cart(self):
        with self.ordered_under('get_active_cart') as lookup:
            # The second look, after the lock found the cart ordered, is real.
            original = services.get_active_cart.side_effect

            def first_stale_then_real(request):
                if lookup.call_count == 1:
                    return original(request)
                return Cart.objects.get_or_create(user=request.user, status=True)[0]

            lookup.side_effect = first_stale_then_real
            response = self.client.post(reverse('cart_add', args=[self.other.pk]),
                                        {'quantity': '3'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lines(), [('Koʻylak', 1)])
        fresh = Cart.objects.get(user=self.user, status=True)
        self.assertNotEqual(fresh.pk, self.cart.pk)
        self.assertEqual([(i.variant.product.name, i.quantity) for i in fresh.cart_items.all()],
                         [('Xudi', 3)])

    def test_the_same_three_writes_work_on_a_cart_nobody_ordered(self):
        self.client.post(reverse('cart_update', args=[self.line.pk]), {'quantity': '4'})
        self.assertEqual(self.lines(), [('Koʻylak', 4)])
        self.client.post(reverse('cart_add', args=[self.other.pk]), {'quantity': '2'})
        self.assertEqual(self.lines(), [('Koʻylak', 4), ('Xudi', 2)])
        self.client.post(reverse('cart_remove', args=[self.line.pk]))
        self.assertEqual(self.lines(), [('Xudi', 2)])

    def test_a_guests_cart_is_written_the_same_way(self):
        """No account, a session's cart: the lock is the cart's, not the user's."""
        self.client.logout()
        self.client.post(reverse('cart_add', args=[self.product.pk]), {'quantity': '2'})
        guest = Cart.objects.get(user__isnull=True, status=True)
        line = guest.cart_items.get()
        self.client.post(reverse('cart_update', args=[line.pk]), {'quantity': '5'})
        line.refresh_from_db()
        self.assertEqual(line.quantity, 5)
        self.client.post(reverse('cart_remove', args=[line.pk]))
        self.assertFalse(guest.cart_items.exists())

    @skipUnless(connection.vendor == 'postgresql', 'SQLite has no row locks to ask for')
    def test_each_write_asks_for_the_carts_row_lock_first(self):
        """The same row the checkout locks, and before the line is touched."""
        posts = [(reverse('cart_update', args=[self.line.pk]), {'quantity': '2'}),
                 (reverse('cart_add', args=[self.other.pk]), {'quantity': '1'}),
                 (reverse('cart_remove', args=[self.line.pk]), {})]
        for url, data in posts:
            with self.subTest(url=url), CaptureQueriesContext(connection) as seen:
                self.client.post(url, data)
            sql = [query['sql'] for query in seen]
            lock = next((i for i, text in enumerate(sql)
                         if 'FROM "cart_cart"' in text and 'FOR UPDATE' in text), None)
            self.assertIsNotNone(lock, 'no lock on the cart for %s' % url)
            written = next(i for i, text in enumerate(sql)
                           if text.startswith(('UPDATE "cart_cartitem"',
                                               'INSERT INTO "cart_cartitem"',
                                               'DELETE FROM "cart_cartitem"')))
            self.assertLess(lock, written, url)
