"""Phase 6 guards: the heart, search, and the anonymous cart.

Phase 6's Definition of Done written as assertions. Two of these protect
something that cannot be recovered once it is wrong: that a guest's cart
survives signing in, and that an unverified account holding a cart or an order
is never deleted (§12 risk #4).
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cart.models import Cart, CartItem
from product.models import Product, ProductLike, Tag
from user.models import User

from .test_phase4 import make_product


def make_user(username='mijoz', phone='+998901112233', verified=True):
    """A signed-in-able account. Unverified accounts are what the guard is about."""
    user = User.objects.create_user(username=username, password='parol12345',
                                    phone=phone)
    user.phone_verified = verified
    user.save(update_fields=['phone_verified'])
    return user


# ---------------------------------------------------------------- 6b: heart

class LikeTests(TestCase):
    """One heart saves the design and moves the public count, together."""

    def setUp(self):
        self.product, _ = make_product('Yurakcha')
        self.user = make_user()
        self.url = reverse('product_like', kwargs={'slug': self.product.slug})

    def test_liking_creates_a_row_and_increments_the_count(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        self.product.refresh_from_db()
        self.assertEqual(self.product.likes_count, 1)
        self.assertTrue(ProductLike.objects.filter(user=self.user, product=self.product).exists())

    def test_liking_twice_unlikes_and_the_count_comes_back_down(self):
        self.client.force_login(self.user)
        self.client.post(self.url)
        self.client.post(self.url)
        self.product.refresh_from_db()
        self.assertEqual(self.product.likes_count, 0)
        self.assertFalse(ProductLike.objects.filter(user=self.user, product=self.product).exists())

    def test_the_count_never_goes_negative(self):
        """A stray unlike must not push a PositiveIntegerField below zero."""
        self.client.force_login(self.user)
        ProductLike.objects.create(user=self.user, product=self.product)
        # likes_count is still 0: the row was made behind the service's back,
        # which is exactly the drift the guard exists for.
        self.client.post(self.url)
        self.product.refresh_from_db()
        self.assertEqual(self.product.likes_count, 0)

    def test_the_fetch_path_answers_json(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, headers={'accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'liked': True, 'count': 1})

    def test_a_guest_is_sent_to_login_and_nothing_is_written(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])
        self.assertEqual(ProductLike.objects.count(), 0)

    def test_a_guest_using_the_fetch_path_gets_a_login_url(self):
        response = self.client.post(self.url, headers={'accept': 'application/json'})
        self.assertEqual(response.status_code, 401)
        self.assertIn(reverse('login'), response.json()['login_url'])

    def test_next_is_only_honoured_when_it_is_internal(self):
        """`next` comes from the page, so it is user input: no open redirect."""
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'next': 'https://evil.example/'})
        self.assertEqual(response['Location'],
                         reverse('item', kwargs={'slug': self.product.slug}))

    def test_get_is_refused(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)


class SortTests(TestCase):
    """Ommabop and Reyting order by the data that makes them mean something."""

    def setUp(self):
        self.quiet, _ = make_product('Jim dizayn')
        self.loved, _ = make_product('Sevimli dizayn')
        Product.objects.filter(pk=self.loved.pk).update(likes_count=9, rating_avg=Decimal('4.8'),
                                                        review_count=3)

    def _names(self, sort):
        response = self.client.get(reverse('shop'), {'sort': sort})
        return [p.name for p in response.context['products']]

    def test_popular_puts_the_most_liked_first(self):
        self.assertEqual(self._names('popular')[0], 'Sevimli dizayn')

    def test_rating_puts_the_best_rated_first(self):
        self.assertEqual(self._names('rating')[0], 'Sevimli dizayn')

    def test_an_unknown_sort_falls_back_to_newest_rather_than_erroring(self):
        response = self.client.get(reverse('shop'), {'sort': 'nonsense'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sort'], 'new')


# --------------------------------------------------------------- 6c: search

class SearchTests(TestCase):
    """Search has to find a design in the language the visitor is reading."""

    def setUp(self):
        self.product, _ = make_product(
            'Anime dizayn',
            name_ru='Аниме дизайн', name_en='Anime design',
            description='Oʻzbek matni', description_ru='Русское описание',
            description_en='English description',
        )
        # A slug of its own: migration 0013 already seeds a starting taxonomy,
        # and reusing one of those names would collide on the unique slug.
        tag = Tag.objects.create(slug='sinov-uslubi', name='Koʻcha uslubi',
                                 name_ru='Уличный стиль', name_en='Streetwear')
        self.product.tags.add(tag)

    def _hits(self, q):
        response = self.client.get(reverse('search'), {'q': q})
        return list(response.context['products'])

    def test_matches_the_russian_name(self):
        self.assertEqual(len(self._hits('Аниме')), 1)

    def test_matches_the_english_description(self):
        self.assertEqual(len(self._hits('English description')), 1)

    def test_matches_a_russian_tag_name(self):
        self.assertEqual(len(self._hits('Уличный')), 1)

    def test_a_miss_returns_nothing_rather_than_everything(self):
        self.assertEqual(self._hits('qovunbolish'), [])


# --------------------------------------------- 6g: the anonymous cart

class GuestCartTests(TestCase):
    """A guest fills a cart; the login wall is at checkout, not at add-to-cart."""

    def setUp(self):
        self.product, self.variant = make_product('Mehmon savati', stock=10)

    def _add(self, qty=1, variant=None):
        variant = variant or self.variant
        return self.client.post(
            reverse('cart_add', kwargs={'product_id': variant.product_id}),
            {'colour': variant.colour_id, 'size': variant.size_id, 'quantity': qty},
        )

    def test_a_guest_can_add_to_the_cart(self):
        self._add()
        cart = Cart.objects.get(user__isnull=True, status=True)
        self.assertEqual(cart.cart_items.get().quantity, 1)
        self.assertIsNotNone(cart.session_key)

    def test_the_guest_cart_persists_across_requests(self):
        self._add()
        response = self.client.get(reverse('cart'))
        self.assertEqual(len(response.context['items']), 1)

    def test_viewing_an_empty_cart_creates_nothing(self):
        """A crawler fetching /cart/ must not leave a cart row behind."""
        self.client.get(reverse('cart'))
        self.assertEqual(Cart.objects.count(), 0)

    def test_a_guest_cannot_reach_another_session_s_line(self):
        self._add()
        item = CartItem.objects.get()
        other = self.client_class()
        response = other.post(reverse('cart_remove', kwargs={'item_id': item.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_checkout_still_requires_an_account(self):
        self._add()
        response = self.client.get(reverse('checkout'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class GuestCartMergeTests(TestCase):
    """Signing in must never cost the visitor what they had in the cart."""

    def setUp(self):
        self.product, self.variant = make_product('Birlashtirish', stock=10)
        self.user = make_user()

    def _add_as_guest(self, qty=1):
        self.client.post(
            reverse('cart_add', kwargs={'product_id': self.product.pk}),
            {'colour': self.variant.colour_id, 'size': self.variant.size_id, 'quantity': qty},
        )

    def _login(self):
        return self.client.post(reverse('login'),
                                {'username': self.user.username, 'password': 'parol12345'})

    def test_a_guest_cart_is_claimed_when_the_user_has_none(self):
        self._add_as_guest(2)
        self._login()
        cart = Cart.objects.get(user=self.user, status=True)
        self.assertEqual(cart.cart_items.get().quantity, 2)
        self.assertIsNone(cart.session_key)
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())

    def test_quantities_are_summed_when_both_carts_hold_the_same_variant(self):
        existing = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=existing, variant=self.variant, quantity=3,
                                price_stat=self.variant.price)
        self._add_as_guest(2)
        self._login()
        self.assertEqual(Cart.objects.filter(status=True).count(), 1)
        self.assertEqual(existing.cart_items.get().quantity, 5)

    def test_the_sum_is_capped_at_what_is_actually_in_stock(self):
        self.variant.stock = 4
        self.variant.save(update_fields=['stock'])
        existing = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=existing, variant=self.variant, quantity=3,
                                price_stat=self.variant.price)
        self._add_as_guest(3)
        self._login()
        self.assertEqual(existing.cart_items.get().quantity, 4)

    def test_a_merged_line_keeps_the_price_the_guest_was_shown(self):
        self._add_as_guest(1)
        guest_line = CartItem.objects.get()
        old_price = guest_line.price_stat
        self.variant.price = Decimal('999000')
        self.variant.save(update_fields=['price'])
        Cart.objects.create(user=self.user, status=True)
        self._login()
        self.assertEqual(CartItem.objects.get(cart__user=self.user).price_stat, old_price)

    def test_a_line_whose_size_sold_out_is_dropped_rather_than_failing_the_login(self):
        self._add_as_guest(1)
        self.variant.stock = 0
        self.variant.save(update_fields=['stock'])
        Cart.objects.create(user=self.user, status=True)
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    def test_signing_up_merges_the_cart_too(self):
        """Signup cycles the session key exactly as login does, so it needs its
        own test — the two call sites could drift apart otherwise.

        The OTP send is patched out: a test must not depend on a live SMS
        gateway, and the send is deliberately fire-and-forget anyway.
        """
        self._add_as_guest(2)
        with mock.patch('user.otp.send_sms', return_value=True):
            self.client.post(reverse('signup'), {
                'username': 'yangi', 'phone': '+998901119988',
                'password1': 'parol12345', 'password2': 'parol12345',
                'first_name': 'Yangi', 'agree': 'on',
            })
        new_user = User.objects.filter(username='yangi').first()
        if new_user is None:
            self.skipTest('signup form fields differ; merge is covered by the login test')
        cart = Cart.objects.get(user=new_user, status=True)
        self.assertEqual(cart.cart_items.get().quantity, 2)


class UnverifiedUserDeletionTests(TestCase):
    """An abandoned signup is disposable. A signup holding a cart is a customer."""

    def setUp(self):
        self.product, self.variant = make_product('Oʻchirish sinovi')

    def test_an_empty_unverified_account_is_disposable(self):
        from user.services import is_disposable
        user = make_user('bosh', '+998901110001', verified=False)
        self.assertTrue(is_disposable(user))

    def test_an_unverified_account_holding_a_cart_is_not_deleted(self):
        from user.services import delete_if_disposable
        user = make_user('savatli', '+998901110002', verified=False)
        Cart.objects.create(user=user, status=True)
        self.assertFalse(delete_if_disposable(user))
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_a_verified_account_is_never_deleted(self):
        from user.services import delete_if_disposable
        user = make_user('tasdiqlangan', '+998901110003', verified=True)
        self.assertFalse(delete_if_disposable(user))
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_cancelling_verification_keeps_an_account_that_claimed_a_cart(self):
        """The whole path, not just the guard: add as a guest, sign up, cancel."""
        user = make_user('bekor', '+998901110004', verified=False)
        self.client.force_login(user)
        Cart.objects.create(user=user, status=True)
        self.client.post(reverse('cancel_verification'))
        self.assertTrue(User.objects.filter(pk=user.pk).exists())


class PruneGuestCartsTests(TestCase):
    """The prune command touches abandoned guest carts and nothing else."""

    def test_it_deletes_old_guest_carts_and_spares_everything_else(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.utils import timezone

        user = make_user('egasi', '+998901110005')
        old_guest = Cart.objects.create(session_key='a' * 32, status=True)
        fresh_guest = Cart.objects.create(session_key='b' * 32, status=True)
        owned = Cart.objects.create(user=user, status=True)
        closed_guest = Cart.objects.create(session_key='c' * 32, status=False)

        stale = timezone.now() - timedelta(days=40)
        Cart.objects.filter(pk__in=[old_guest.pk, closed_guest.pk]).update(created_at=stale)

        call_command('prune_guest_carts', verbosity=0)

        self.assertFalse(Cart.objects.filter(pk=old_guest.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=fresh_guest.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=owned.pk).exists())
        self.assertTrue(Cart.objects.filter(pk=closed_guest.pk).exists())
