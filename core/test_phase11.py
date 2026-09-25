"""Phase 11: what is not on sale cannot be bought.

`is_active=False` hid a product from the shop, the sitemap and its own page,
and from nothing else: a POST naming its id put it in a cart, and a product
switched off while it sat in a cart went through checkout (§17 #294). These
tests hold the cart, the checkout view and the order service to the one rule
`VariantQuerySet.on_sale` already stated.
"""
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from cart.models import Cart, CartItem
from payment import services
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user


class OffSaleTests(TestCase):
    """A switched-off product or an unavailable size never becomes an order."""

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('sotuv', '+998901290077')
        self.product, self.variant = make_product('Yopilgan', stock=5)

    def _cart(self, *variants):
        cart = Cart.objects.create(user=self.user, status=True)
        for variant in variants or (self.variant,):
            CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                    price_stat=variant.price)
        return cart

    def _switch_off(self, product=None):
        product = product or self.product
        product.is_active = False
        product.save(update_fields=['is_active'])

    def _checkout(self):
        self.client.force_login(self.user)
        return self.client.post(reverse('checkout'), {
            'name': 'Dilnoza Karimova', 'phone': '+998 90 129 00 77',
            'delivery_option': 'uzpost_office',
            'region': self.geo['tashkent'].pk,
            'district': self.geo['chilonzor'].pk,
            'postal_index': '100011',
            'payment_method': 'click', 'notes': '',
        })

    def _messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    # ------------------------------------------------------------------ cart

    def test_a_switched_off_product_cannot_be_added(self):
        """Refused with the message a size taken off sale already gets, and
        sent to the shop - the product's own page is a 404 by now."""
        self._switch_off()
        response = self.client.post(
            reverse('cart_add', args=[self.product.pk]),
            {'size': self.variant.size_id, 'quantity': 1})
        self.assertRedirects(response, reverse('shop'), fetch_redirect_response=False)
        self.assertFalse(CartItem.objects.exists())
        self.assertIn('Ushbu tovar sotuvda yoʻq', self._messages(response))

    def test_an_active_product_is_added_as_before(self):
        """The control: the same POST for a product on sale adds the line."""
        self.client.post(reverse('cart_add', args=[self.product.pk]),
                         {'size': self.variant.size_id, 'quantity': 1})
        self.assertEqual(CartItem.objects.count(), 1)

    def test_the_cart_marks_a_line_that_went_off_sale(self):
        """The line stays so it can be removed, flagged, and linked nowhere."""
        self._cart()
        self._switch_off()
        self.client.force_login(self.user)
        page = self.client.get(reverse('cart')).content.decode()
        self.assertIn('Sotuvda yoʻq', page)
        self.assertNotIn('href="%s"' % self.product.get_absolute_url(), page)

    def test_a_line_on_sale_is_not_marked(self):
        self._cart()
        self.client.force_login(self.user)
        page = self.client.get(reverse('cart')).content.decode()
        self.assertNotIn('Sotuvda yoʻq', page)
        self.assertIn('href="%s"' % self.product.get_absolute_url(), page)

    # -------------------------------------------------------------- checkout

    def test_an_on_sale_cart_checks_out(self):
        """The control for everything below: this POST is a valid order, so a
        refusal further down cannot pass because the form was wrong."""
        cart = self._cart()
        self._checkout()
        self.assertTrue(Order.objects.filter(cart=cart).exists())

    def test_the_checkout_page_sends_the_cart_back_before_the_form(self):
        self._cart()
        self._switch_off()
        self.client.force_login(self.user)
        response = self.client.get(reverse('checkout'))
        self.assertRedirects(response, reverse('cart'), fetch_redirect_response=False)
        self.assertIn('Yopilgan endi sotuvda yoʻq. Buyurtma berish uchun uni savatdan '
                      'olib tashlang.', self._messages(response))

    def test_a_switched_off_product_is_not_ordered(self):
        cart = self._cart()
        self._switch_off()
        response = self._checkout()
        self.assertRedirects(response, reverse('cart'), fetch_redirect_response=False)
        self.assertFalse(Order.objects.exists())
        cart.refresh_from_db()
        self.assertTrue(cart.status, 'the cart must stay open to be fixed')

    def test_a_size_taken_off_sale_is_not_ordered(self):
        self._cart()
        self.variant.available = False
        self.variant.save(update_fields=['available'])
        self._checkout()
        self.assertFalse(Order.objects.exists())

    def test_the_service_refuses_under_the_lock(self):
        """The view's check runs before the form; this is the one that holds
        if the product is switched off between the two."""
        cart = self._cart()
        self._switch_off()
        with self.assertRaises(services.OffSaleItems) as caught:
            services.create_order_from_cart(
                self.user, cart, phone='+998 90 129 00 77', address='',
                notes='', payment_method='click')
        self.assertEqual([line.variant for line in caught.exception.lines], [self.variant])
        self.assertFalse(Order.objects.exists())

    def test_two_products_are_named_once_each_and_in_the_plural(self):
        other, other_variant = make_product('Olingan', stock=5)
        self._cart(self.variant, other_variant)
        self._switch_off()
        self._switch_off(other)
        self.client.force_login(self.user)
        response = self.client.get(reverse('checkout'))
        self.assertIn('Yopilgan, Olingan endi sotuvda yoʻq. Buyurtma berish uchun ularni '
                      'savatdan olib tashlang.', self._messages(response))

    def test_the_refusal_is_written_in_each_language(self):
        """Read off the rendered cart page, one and two products, so both
        plural forms are exercised in the two languages that have them
        (§17 #255)."""
        other, other_variant = make_product('Olingan', stock=5)
        self._cart(self.variant, other_variant)
        self._switch_off()
        self.client.force_login(self.user)
        expected = {
            'ru': ['больше не продаётся', 'удалите его из корзины'],
            'en': ['is no longer on sale', 'Remove it from your cart'],
        }
        for language, words in expected.items():
            with self.subTest(language=language, count=1), translation.override(language):
                page = self.client.get(reverse('checkout'), follow=True).content.decode()
                for phrase in words:
                    self.assertIn(phrase, page)
        self._switch_off(other)
        plural = {
            'ru': ['больше не продаются', 'удалите их из корзины'],
            'en': ['are no longer on sale', 'Remove them from your cart'],
        }
        for language, words in plural.items():
            with self.subTest(language=language, count=2), translation.override(language):
                page = self.client.get(reverse('checkout'), follow=True).content.decode()
                for phrase in words:
                    self.assertIn(phrase, page)
