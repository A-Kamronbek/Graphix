"""Smoke tests: the four paths that must never break silently.

Kept deliberately small and fast so they can run on every branch through the
rebuild as a catastrophic-breakage check — the home page and shop render, a user
can log in, and a cart becomes an order. Per-app coverage arrives in Phase 10.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from payment.models import Order
from product.models import Category, Colour, Product, Size, Variant
from user.models import User


class SmokeTests(TestCase):
    """One test per critical path: home, shop, login, checkout."""

    @classmethod
    def setUpTestData(cls):
        """Create the smallest account and catalogue the four paths need.

        ``phone_verified`` is set so PhoneVerificationMiddleware doesn't bounce
        the logged-in requests to the OTP screen.
        """
        cls.password = 'smoke-test-pass-123'
        cls.user = User.objects.create_user(
            username='smokeuser',
            password=cls.password,
            phone='+998 90 123 45 67',
            phone_verified=True,
        )
        cls.product = Product.objects.create(
            name='Smoke tee',
            category=Category.objects.create(name='Futbolka'),
        )
        cls.variant = Variant.objects.create(
            product=cls.product,
            size=Size.objects.create(size='M'),
            colour=Colour.objects.create(colour='Qora'),
            price=Decimal('150000'),
            available=True,
        )

    def test_home_renders(self):
        """The home page returns 200 for an anonymous visitor."""
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_shop_renders(self):
        """The shop returns 200 and lists the available product."""
        response = self.client.get(reverse('shop'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product, list(response.context['products']))

    def test_login_works(self):
        """Valid credentials authenticate the session and land on the shop."""
        response = self.client.post(
            reverse('login'),
            {'username': 'smokeuser', 'password': self.password},
        )
        self.assertRedirects(response, reverse('shop'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_checkout_creates_order(self):
        """A cart with one line becomes an Order, and the cart closes behind it."""
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            variant=self.variant,
            quantity=2,
            price_stat=self.variant.price,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse('checkout'), {
            'name': 'Smoke User',
            'phone': '+998 90 123 45 67',
            'address': 'Toshkent, Amir Temur ko\'chasi 1',
            'notes': '',
            'payment_method': Order.PaymentMethod.CLICK,
        })

        order = Order.objects.get(cart=cart)
        self.assertRedirects(response, reverse('payment', args=[order.id]))
        self.assertEqual(order.total_price, Decimal('300000'))
        self.assertEqual(order.status, Order.Status.PAYING)

        cart.refresh_from_db()
        self.assertFalse(cart.status, "checkout must close the cart it consumed")
