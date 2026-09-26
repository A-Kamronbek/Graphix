"""The report tiles on the panel's dashboard count sales and nothing else.

"Bugungi buyurtmalar", "Bugungi tushum", "Shu hafta" and "Haftalik tushum"
used to exclude `paying` and keep everything else, so a cancelled order that
was never paid sat in today's takings as money (§17 #297). A sale is an order
that was paid for and kept: paid, being packed, on the way, or delivered.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from panel.views import SOLD
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff


class DashboardSalesTests(TestCase):
    """Each tile against a day that holds every status at once."""

    def setUp(self):
        self.staff = make_staff('hisobchi', '+998901229401')
        self.customer = make_user('xaridor', '+998901229402')
        self.product, self.variant = make_product('Savdo', stock=20)
        self.client.force_login(self.staff)

    def _order(self, status, total):
        """An order placed today, in ``status``, worth ``total``."""
        cart = Cart.objects.create(user=self.customer, status=False)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)
        return Order.objects.create(user=self.customer, cart=cart,
                                    phone=self.customer.phone, address='Test',
                                    total_price=Decimal(total), status=status)

    def context(self):
        return self.client.get(reverse('panel_dashboard')).context

    def test_a_cancelled_order_is_not_a_sale(self):
        """The case that was reported: cancelled, 164 000, counted as takings."""
        self._order('cancelled', 164000)
        ctx = self.context()
        self.assertEqual(ctx['orders_today'], 0)
        self.assertEqual(ctx['revenue_today'], 0)
        self.assertEqual(ctx['orders_week'], 0)
        self.assertEqual(ctx['revenue_week'], 0)

    def test_every_stage_after_payment_is_a_sale(self):
        """Paid, packing, on the way and delivered all count; the rest do not."""
        self._order('paying', 1000000)
        self._order('cancelled', 2000000)
        self._order('paid', 1000)
        self._order('processing', 2000)
        self._order('on_the_way', 3000)
        self._order('done', 4000)
        ctx = self.context()
        self.assertEqual(ctx['orders_today'], 4)
        self.assertEqual(ctx['revenue_today'], Decimal('10000'))
        self.assertEqual(ctx['orders_week'], 4)
        self.assertEqual(ctx['revenue_week'], Decimal('10000'))

    def test_the_work_tiles_are_unchanged(self):
        """Waiting-for-payment still shows the unpaid order; it is work, not a sale."""
        self._order('paying', 5000)
        self._order('cancelled', 5000)
        ctx = self.context()
        self.assertEqual(ctx['awaiting'], 1)
        self.assertEqual(ctx['to_pack'], 0)

    def test_every_status_is_decided(self):
        """A status added to Order later has to be placed on one side or the other.

        Without this, a new status would silently drop out of the takings and
        nobody would notice until the numbers looked low.
        """
        self.assertEqual(set(Order.Status.values) - set(SOLD),
                         {'paying', 'cancelled'})
