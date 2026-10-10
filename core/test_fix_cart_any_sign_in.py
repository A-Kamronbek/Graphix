"""Signing in never costs the visitor what they put in the cart, by any door.

The merge used to be two lines in two views, the storefront's sign-in and its
sign-up. The Django admin has a sign-in form of its own, which the owner and
the staff use, and it merged nothing: somebody who filled a cart as a guest and
then signed in there found their account's old cart and none of the new lines.

The merge now hangs off Django's own signed-in signal, so it happens wherever
``login()`` is called. These tests come in by each door.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from user.models import User

from .test_phase4 import make_product

PASSWORD = 'parol12345'


def account(username, phone, staff=False):
    """A verified account that can sign in with a password."""
    user = User.objects.create_user(username=username, password=PASSWORD, phone=phone)
    user.phone_verified = True
    user.is_staff = user.is_superuser = staff
    user.save()
    return user


class AnySignInMergesTheCartTests(TestCase):
    """An account with a cart already; a guest adds something else; then signs in."""

    def setUp(self):
        # Sign-in is rate limited per name, and the counters outlive a test.
        cache.clear()
        self.addCleanup(cache.clear)
        self.old, self.old_variant = make_product('Eski tanlov', stock=10)
        self.new, self.new_variant = make_product('Yangi tanlov', stock=10)

    def cart_of(self, user):
        """An open cart for ``user`` holding one of the old product."""
        cart = Cart.objects.create(user=user, status=True)
        CartItem.objects.create(cart=cart, variant=self.old_variant, quantity=1,
                                price_stat=self.old_variant.price)
        return cart

    def add_as_guest(self, variant, quantity=1):
        product = variant.product
        self.client.post(
            reverse('cart_add', kwargs={'product_id': product.pk}),
            {'colour': variant.colour_id, 'size': variant.size_id, 'quantity': quantity},
        )

    def lines(self, user):
        """What the account's open cart holds, as {product name: quantity}."""
        cart = Cart.objects.get(user=user, status=True)
        return {line.variant.product.name: line.quantity
                for line in cart.cart_items.select_related('variant__product')}

    def test_the_storefront_door_at_checkout(self):
        user = account('mijoz', '+998901112201')
        self.cart_of(user)
        self.add_as_guest(self.new_variant)
        # The checkout is what sends a guest to sign in, with the way back.
        sent = self.client.get(reverse('checkout'))
        self.assertIn(reverse('login'), sent['Location'])
        self.client.post(sent['Location'], {'username': 'mijoz', 'password': PASSWORD})
        self.assertEqual(self.lines(user), {'Eski tanlov': 1, 'Yangi tanlov': 1})
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())

    def test_the_admin_door(self):
        owner = account('egasi', '+998901112202', staff=True)
        self.cart_of(owner)
        self.add_as_guest(self.new_variant)
        response = self.client.post('/admin/login/', {'username': 'egasi', 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.lines(owner), {'Eski tanlov': 1, 'Yangi tanlov': 1})
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())

    def test_the_cart_is_merged_once(self):
        """Two of the same thing as a guest and one already: three, not five."""
        user = account('mijoz', '+998901112203')
        self.cart_of(user)
        self.add_as_guest(self.old_variant, quantity=2)
        self.client.post(reverse('login'), {'username': 'mijoz', 'password': PASSWORD})
        self.assertEqual(self.lines(user), {'Eski tanlov': 3})

    def test_an_account_with_no_cart_takes_the_guests(self):
        user = account('mijoz', '+998901112204')
        self.add_as_guest(self.new_variant, quantity=2)
        self.client.post(reverse('login'), {'username': 'mijoz', 'password': PASSWORD})
        self.assertEqual(self.lines(user), {'Yangi tanlov': 2})

    def test_a_sign_in_with_no_guest_session_changes_nothing(self):
        user = account('mijoz', '+998901112205')
        self.cart_of(user)
        self.client.force_login(user)
        self.assertEqual(self.lines(user), {'Eski tanlov': 1})

    def test_another_visitors_guest_cart_is_left_alone(self):
        """The merge takes the cart of the session that signed in, and no other."""
        user = account('mijoz', '+998901112206')
        self.add_as_guest(self.new_variant)
        stranger = self.client_class()
        stranger.post(reverse('login'), {'username': 'mijoz', 'password': PASSWORD})
        self.assertFalse(Cart.objects.filter(user=user).exists())
        self.assertTrue(Cart.objects.filter(user__isnull=True, status=True).exists())
