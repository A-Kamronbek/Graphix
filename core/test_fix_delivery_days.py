"""Delivery times beside the delivery prices: 1–2 kun to a post office, 1–6 to the door.

The owner's figures (§17 #301), kept on the DeliveryOption rows beside the
price, so a change is a panel edit rather than a deploy - the reason the prices
are rows (§18 #18). Shown on the product page, at checkout and on the delivery
page. The checkout's old footnote, which said 1–6 days to a post office and
one more to the door, is gone, because it would contradict the rows. The terms
keep their wider "odatda 1–6 kun" (legal.TRANSIT_DAYS), which covers both.
"""
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from core.templatetags.legal_tags import legal_range
from payment.models import DeliveryOption

from .test_phase4 import make_product
from .test_phase6 import make_user

OFFICE = legal_range(1, 2)
DOOR = legal_range(1, 6)


class DeliveryDaysTests(TestCase):
    """The figures, the words around them, and every page that shows them."""

    def setUp(self):
        self.office = DeliveryOption.objects.get(code='uzpost_office')
        self.door = DeliveryOption.objects.get(code='uzpost_door')

    def test_the_owners_figures_are_on_the_rows(self):
        """Set by the migration, on the rows that were already there."""
        self.assertEqual((self.office.days_min, self.office.days_max), (1, 2))
        self.assertEqual((self.door.days_min, self.door.days_max), (1, 6))

    def test_the_label_in_each_language(self):
        """Russian agrees with the upper figure: 1–2 дня, 1–6 дней."""
        expected = {
            'uz': (OFFICE + ' kun', DOOR + ' kun'),
            'ru': (OFFICE + ' дня', DOOR + ' дней'),
            'en': (OFFICE + ' days', DOOR + ' days'),
        }
        for lang, (office, door) in expected.items():
            with translation.override(lang):
                self.assertEqual(self.office.days_label, office, lang)
                self.assertEqual(self.door.days_label, door, lang)

    def test_one_figure_and_no_figure(self):
        """The same figure twice is one figure; a most of 0 states nothing."""
        self.door.days_min = self.door.days_max = 1
        with translation.override('en'):
            self.assertEqual(self.door.days_label, '1 day')
        self.door.days_max = 0
        self.assertEqual(self.door.days_label, '')

    def test_the_product_page_shows_them_under_each_name(self):
        product, _variant = make_product('Muddat', stock=5)
        html = self.client.get(reverse('item', args=[product.slug])).content.decode()
        self.assertIn('<span class="spec__sub">%s kun</span>' % OFFICE, html)
        self.assertIn('<span class="spec__sub">%s kun</span>' % DOOR, html)

    def test_a_row_with_no_time_shows_none(self):
        DeliveryOption.objects.filter(pk=self.door.pk).update(days_max=0)
        product, _variant = make_product('Muddatsiz', stock=5)
        html = self.client.get(reverse('item', args=[product.slug])).content.decode()
        self.assertEqual(html.count('class="spec__sub"'), 1)

    def test_checkout_shows_them_and_not_the_old_footnote(self):
        user = make_user('muddatchi', '+998901290301')
        _product, variant = make_product('Kassa', stock=5)
        cart = Cart.objects.create(user=user, status=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                price_stat=variant.price)
        self.client.force_login(user)
        html = self.client.get(reverse('checkout')).content.decode()
        self.assertIn(OFFICE + ' kun · ', html)
        self.assertIn(DOOR + ' kun · ', html)
        self.assertNotIn('yana bir kun', html)

    def test_the_delivery_page_shows_them_in_each_language(self):
        for lang, office, gone in (('uz', OFFICE + ' kun', 'yana bir kun'),
                                   ('ru', OFFICE + ' дня', 'ещё день'),
                                   ('en', OFFICE + ' days', 'one more day')):
            with translation.override(lang):
                html = self.client.get(reverse('delivery')).content.decode()
            self.assertIn(office, html, lang)
            self.assertNotIn(gone, html, lang)

    def test_the_panel_can_edit_them(self):
        """Beside the price, in the same card, read the way a count is."""
        from panel.reference import EDITABLE
        fields = EDITABLE['delivery'][1]
        self.assertEqual((fields['days_min'], fields['days_max']), ('count', 'count'))
