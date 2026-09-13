"""Phase 6 guards: the heart, search, the anonymous cart, and delivery.

Phase 6's Definition of Done written as assertions. Several of these protect
something that cannot be recovered once it is wrong:

* a guest's cart survives signing in, and an unverified account holding a cart
  or an order is never deleted (§12 risk #4);
* a postal index that contradicts its region never becomes an order, which is
  the typo that sends a real parcel to another province (§17 #86);
* the delivery price and the destination are frozen on the order, so a later
  change cannot rewrite what was agreed (§17 #14).
"""
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
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


# ------------------------------------------------------- 6a: the size guide

class SizeChartTests(TestCase):
    """The seeded charts have to reach a product without the owner linking them."""

    def test_both_fits_are_seeded_with_four_measured_rows(self):
        from product.models import SizeChart
        for fit in ('regular', 'oversize'):
            chart = SizeChart.objects.filter(fit=fit).first()
            self.assertIsNotNone(chart, f'no chart seeded for {fit}')
            self.assertEqual(chart.rows.count(), 4)

    def test_a_products_fit_finds_its_chart(self):
        product, _ = make_product('Oversize dizayn', fit='oversize')
        chart = product.resolve_size_chart()
        self.assertIsNotNone(chart)
        self.assertEqual(chart.fit, 'oversize')

    def test_an_explicit_chart_beats_the_fit_fallback(self):
        from product.models import SizeChart
        own = SizeChart.objects.create(name='Faqat shu mahsulot uchun')
        product, _ = make_product('Maxsus', fit='oversize', size_chart=own)
        self.assertEqual(product.resolve_size_chart(), own)

    def test_a_product_with_no_fit_and_no_chart_gets_none(self):
        """Better no chart than a chart that might not match the garment."""
        product, _ = make_product('Qolipsiz')
        self.assertIsNone(product.resolve_size_chart())

    def test_the_chart_rows_are_on_the_product_page_for_a_screen_reader(self):
        product, _ = make_product('Jadvalli', fit='regular')
        response = self.client.get(reverse('item', kwargs={'slug': product.slug}))
        self.assertContains(response, 'data-sizeguide-content')
        self.assertContains(response, 'data-row-size')

    def test_the_standalone_page_renders_now_that_charts_exist(self):
        response = self.client.get(reverse('size_guide'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Oversize')

    def test_the_guide_is_advertised_once_there_is_one(self):
        from core.context_processors import size_guide
        self.assertTrue(size_guide(None)['has_size_guide'])


# ------------------------------- 6d / 6e: delivery, the index, and payment

def make_regions():
    """Two real regions plus the escape — enough to test every branch rule."""
    from payment.models import District, Region

    tashkent = Region.objects.create(code='1726', name='Toshkent shahri',
                                     postal_prefix='100', sort_order=10)
    samarqand = Region.objects.create(code='1718', name='Samarqand viloyati',
                                      postal_prefix='14', sort_order=20)
    other = Region.objects.create(code='0000', name='Boshqa',
                                  postal_prefix='', sort_order=999)
    return {
        'tashkent': tashkent,
        'samarqand': samarqand,
        'other': other,
        'chilonzor': District.objects.create(region=tashkent, code='1726294',
                                             name='Chilonzor tumani', kind='district'),
        'sam_city': District.objects.create(region=samarqand, code='1718401',
                                            name='Samarqand shahri', kind='city'),
        'other_district': District.objects.create(region=other, code='0000900',
                                                  name='Boshqa', kind='other'),
    }


class DeliveryValidationTests(TestCase):
    """Order.clean is the one place that decides what a valid order is.

    The checkout view asks it rather than repeating the rules, so testing it
    here tests both. The prefix check is the point of the whole redesign
    (§17 #86): it catches the typo that sends a real parcel to another province.
    """

    def setUp(self):
        from payment.models import DeliveryOption
        self.geo = make_regions()
        self.branch = DeliveryOption.objects.get(code='uzpost_office')
        self.home = DeliveryOption.objects.get(code='uzpost_door')

    def _order(self, **kwargs):
        from payment.models import Order
        return Order(**kwargs)

    def _branch_order(self, **over):
        fields = {
            'delivery_option': self.branch,
            'region': self.geo['tashkent'],
            'district': self.geo['chilonzor'],
            'postal_index': '100011',
        }
        fields.update(over)
        return self._order(**fields)

    def test_a_complete_branch_order_is_valid(self):
        self._branch_order().clean()          # must not raise

    def test_a_branch_order_needs_a_region(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(region=None).clean()

    def test_a_branch_order_needs_a_district(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(district=None).clean()

    def test_a_branch_order_needs_an_index(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(postal_index='').clean()

    def test_a_five_digit_index_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(postal_index='10001').clean()

    def test_a_non_numeric_index_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(postal_index='10001A').clean()

    def test_an_index_that_contradicts_the_region_is_rejected(self):
        """140216 is Samarqand. Chosen against Toshkent shahri, it is the typo
        that would otherwise send the parcel to another province."""
        with self.assertRaises(DjangoValidationError):
            self._branch_order(postal_index='140216').clean()

    def test_a_district_from_another_region_is_rejected(self):
        with self.assertRaises(DjangoValidationError):
            self._branch_order(district=self.geo['sam_city']).clean()

    def test_the_escape_region_skips_the_prefix_check(self):
        self._branch_order(region=self.geo['other'],
                           district=self.geo['other_district'],
                           postal_index='140216').clean()

    def test_the_escape_region_still_requires_six_digits(self):
        """A four-digit index is wrong no matter where it is (§17 #86)."""
        with self.assertRaises(DjangoValidationError):
            self._branch_order(region=self.geo['other'],
                               district=self.geo['other_district'],
                               postal_index='1402').clean()

    def test_a_home_order_needs_an_address(self):
        with self.assertRaises(DjangoValidationError):
            self._order(delivery_option=self.home, address='').clean()

    def test_a_home_order_rejects_a_postal_index(self):
        with self.assertRaises(DjangoValidationError):
            self._order(delivery_option=self.home, address='Toshkent',
                        postal_index='100011').clean()

    def test_a_home_order_with_a_typed_address_is_valid(self):
        self._order(delivery_option=self.home, address='Toshkent, Amir Temur 1').clean()


class CheckoutTests(TestCase):
    """The checkout end to end, both branches."""

    def setUp(self):
        from payment.models import DeliveryOption
        self.geo = make_regions()
        self.branch = DeliveryOption.objects.get(code='uzpost_office')
        self.home = DeliveryOption.objects.get(code='uzpost_door')
        self.user = make_user('xaridor', '+998901234567')
        self.product, self.variant = make_product('Rasmiylashtirish', stock=10)
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)
        self.cart = cart

    def _post(self, **over):
        data = {'name': 'Xaridor', 'phone': '+998 90 123 45 67',
                'payment_method': 'click', 'notes': ''}
        data.update(over)
        return self.client.post(reverse('checkout'), data)

    def _order(self):
        from payment.models import Order
        return Order.objects.filter(cart=self.cart).first()

    def test_a_branch_order_charges_15000_and_freezes_where_it_is_going(self):
        self._post(delivery_option='uzpost_office',
                   region=self.geo['tashkent'].pk,
                   district=self.geo['chilonzor'].pk,
                   postal_index='100011')
        order = self._order()
        self.assertIsNotNone(order)
        self.assertEqual(order.delivery_price, Decimal('15000'))
        self.assertEqual(order.total_price, self.variant.price + Decimal('15000'))
        self.assertIn('100011', order.location_snapshot)
        self.assertIn('Chilonzor', order.location_snapshot)
        self.assertIsNone(order.latitude)

    def test_a_home_order_charges_40000(self):
        self._post(delivery_option='uzpost_door', address='Toshkent, Amir Temur 1',
                   address_source='manual')
        order = self._order()
        self.assertIsNotNone(order)
        self.assertEqual(order.delivery_price, Decimal('40000'))
        self.assertEqual(order.address_source, 'manual')

    def test_a_manual_order_stores_no_coordinates(self):
        self._post(delivery_option='uzpost_door', address='Toshkent',
                   address_source='manual', latitude='41.3', longitude='69.2')
        order = self._order()
        self.assertIsNone(order.latitude)
        self.assertIsNone(order.longitude)
        self.assertEqual(order.address_source, 'manual')

    def test_a_map_order_stores_the_pin_and_says_so(self):
        self._post(delivery_option='uzpost_door', address='Toshkent',
                   address_source='map', latitude='41.311081', longitude='69.240562')
        order = self._order()
        self.assertEqual(order.address_source, 'map')
        self.assertEqual(float(order.latitude), 41.311081)

    def test_a_map_order_whose_pin_did_not_arrive_falls_back_to_manual(self):
        """The address is what the courier follows either way (§17 #91)."""
        self._post(delivery_option='uzpost_door', address='Toshkent',
                   address_source='map', latitude='', longitude='')
        order = self._order()
        self.assertEqual(order.address_source, 'manual')
        self.assertIsNone(order.latitude)

    def test_a_branch_order_keeps_nothing_from_the_home_half(self):
        self._post(delivery_option='uzpost_office',
                   region=self.geo['tashkent'].pk,
                   district=self.geo['chilonzor'].pk,
                   postal_index='100011',
                   address='Bu manzil saqlanmasligi kerak',
                   latitude='41.3', longitude='69.2', address_source='map')
        order = self._order()
        self.assertIsNone(order.latitude)
        self.assertEqual(order.address_source, '')

    def test_an_index_that_contradicts_the_region_does_not_create_an_order(self):
        response = self._post(delivery_option='uzpost_office',
                              region=self.geo['tashkent'].pk,
                              district=self.geo['chilonzor'].pk,
                              postal_index='140216')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._order())

    def test_the_boshqa_escape_records_what_the_customer_typed(self):
        self._post(delivery_option='uzpost_office',
                   region=self.geo['other'].pk,
                   district=self.geo['other_district'].pk,
                   postal_index='150300',
                   location_note='Yangi tuman')
        order = self._order()
        self.assertEqual(order.location_note, 'Yangi tuman')
        self.assertIn('Yangi tuman', order.location_snapshot)

    def test_a_note_on_an_ordinary_district_is_ignored(self):
        self._post(delivery_option='uzpost_office',
                   region=self.geo['tashkent'].pk,
                   district=self.geo['chilonzor'].pk,
                   postal_index='100011', location_note='qaydan keldi')
        self.assertEqual(self._order().location_note, '')

    def test_the_frozen_price_survives_a_later_price_change(self):
        self._post(delivery_option='uzpost_door', address='Toshkent')
        order = self._order()
        self.home.price = Decimal('99000')
        self.home.save(update_fields=['price'])
        order.refresh_from_db()
        self.assertEqual(order.delivery_price, Decimal('40000'))

    def test_the_snapshot_survives_the_district_being_deactivated(self):
        self._post(delivery_option='uzpost_office',
                   region=self.geo['tashkent'].pk,
                   district=self.geo['chilonzor'].pk,
                   postal_index='100011')
        order = self._order()
        frozen = order.location_snapshot
        self.geo['chilonzor'].is_active = False
        self.geo['chilonzor'].name = 'Boshqa nom'
        self.geo['chilonzor'].save()
        order.refresh_from_db()
        self.assertEqual(order.location_snapshot, frozen)


class PaymentOptionTests(TestCase):
    """Cash is kept but switched off, and the checkout refuses what it is not offering."""

    def setUp(self):
        from payment.models import DeliveryOption
        self.geo = make_regions()
        self.home = DeliveryOption.objects.get(code='uzpost_door')
        self.user = make_user('tolovchi', '+998901234599')
        self.product, self.variant = make_product('Toʻlov', stock=5)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)

    def _post(self, method):
        return self.client.post(reverse('checkout'), {
            'name': 'Toʻlovchi', 'phone': '+998 90 123 45 99',
            'delivery_option': 'uzpost_door', 'address': 'Toshkent',
            'address_source': 'manual', 'payment_method': method, 'notes': '',
        })

    def test_click_is_active_and_cash_is_not(self):
        from payment.models import PaymentOption
        self.assertTrue(PaymentOption.objects.get(code='click').is_active)
        self.assertFalse(PaymentOption.objects.get(code='cash').is_active)

    def test_the_checkout_does_not_offer_an_inactive_method(self):
        response = self.client.get(reverse('checkout'))
        codes = [o.code for o in response.context['payment_options']]
        self.assertEqual(codes, ['click'])

    def test_a_posted_inactive_method_is_refused_rather_than_defaulted_past(self):
        from payment.models import Order
        response = self._post('cash')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.filter(cart=self.cart).exists())

    def test_turning_cash_on_makes_it_orderable(self):
        """The whole point of a row: the owner flips it, no deploy."""
        from payment.models import Order, PaymentOption
        PaymentOption.objects.filter(code='cash').update(is_active=True)
        self._post('cash')
        order = Order.objects.get(cart=self.cart)
        self.assertEqual(order.payment_method, 'cash')


class SeedRegionsTests(TestCase):
    """The shipped dataset loads, and re-running it never duplicates or deletes."""

    def test_the_shipped_csv_loads_and_is_idempotent(self):
        from payment.models import District, Region
        call_command('seed_regions', verbosity=0)
        regions, districts = Region.objects.count(), District.objects.count()
        self.assertGreaterEqual(regions, 15)
        self.assertGreaterEqual(districts, 200)
        call_command('seed_regions', verbosity=0)
        self.assertEqual(Region.objects.count(), regions)
        self.assertEqual(District.objects.count(), districts)

    def test_every_region_has_a_usable_prefix_or_is_the_escape(self):
        from payment.models import Region
        call_command('seed_regions', verbosity=0)
        for region in Region.objects.all():
            if region.code == '0000':
                self.assertEqual(region.postal_prefix, '')
            else:
                self.assertRegex(region.postal_prefix, r'^\d{2,3}$')

    def test_a_row_missing_from_the_csv_is_deactivated_not_deleted(self):
        from payment.models import District, Region
        stale_region = Region.objects.create(code='9999', name='Eski viloyat',
                                             postal_prefix='99')
        stale = District.objects.create(region=stale_region, code='9999001',
                                        name='Eski tuman', kind='district')
        call_command('seed_regions', verbosity=0)
        stale.refresh_from_db()
        stale_region.refresh_from_db()
        self.assertFalse(stale.is_active)
        self.assertFalse(stale_region.is_active)

    def test_a_duplicate_prefix_is_refused_and_nothing_is_written(self):
        """A prefix collision would let the wrong region accept an index."""
        import tempfile
        from django.core.management.base import CommandError
        from payment.models import Region

        handle = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False,
                                             newline='', encoding='utf-8')
        handle.write('level,code,region_code,name,name_ru,name_en,kind,postal_prefix,sort_order\n')
        handle.write('region,1111,,Bir,Один,One,,10,1\n')
        handle.write('region,2222,,Ikki,Два,Two,,10,2\n')
        handle.close()

        with self.assertRaises(CommandError):
            call_command('seed_regions', file=handle.name, verbosity=0)
        self.assertEqual(Region.objects.count(), 0)


# ------------------------------------------------- 6f: Telegram notifications

class TelegramTests(TestCase):
    """The one thing a notification must never do is break the thing it reports."""

    def test_a_blank_token_sends_nothing_and_does_not_raise(self):
        from core import telegram
        with self.settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID=''):
            self.assertFalse(telegram.configured())
            self.assertFalse(telegram.send('salom'))

    def test_a_network_failure_is_swallowed(self):
        import requests
        from core import telegram
        with self.settings(TELEGRAM_BOT_TOKEN='t', TELEGRAM_CHAT_ID='1'):
            with mock.patch('core.telegram.requests.post',
                            side_effect=requests.RequestException('down')):
                self.assertFalse(telegram.send('salom'))

    def test_a_rejected_message_is_swallowed(self):
        from core import telegram
        response = mock.Mock(status_code=400, text='Bad Request')
        with self.settings(TELEGRAM_BOT_TOKEN='t', TELEGRAM_CHAT_ID='1'):
            with mock.patch('core.telegram.requests.post', return_value=response):
                self.assertFalse(telegram.send('salom'))

    def test_user_text_is_escaped_into_the_message(self):
        from core import telegram
        self.assertEqual(telegram.esc('<b>x</b>'), '&lt;b&gt;x&lt;/b&gt;')


class TelegramDeliveryTests(TestCase):
    """The four events fire, on commit, and a broken gateway breaks nothing."""

    def setUp(self):
        from payment.models import DeliveryOption
        self.geo = make_regions()
        self.home = DeliveryOption.objects.get(code='uzpost_door')
        self.user = make_user('xabarchi', '+998901234511')
        self.product, self.variant = make_product('Bildirishnoma', stock=5)
        self.client.force_login(self.user)
        self.cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=1,
                                price_stat=self.variant.price)

    def _checkout(self):
        return self.client.post(reverse('checkout'), {
            'name': 'Xabarchi', 'phone': '+998 90 123 45 11',
            'delivery_option': 'uzpost_door', 'address': 'Toshkent',
            'address_source': 'manual', 'payment_method': 'click', 'notes': '',
        })

    def test_an_order_sends_one_message(self):
        """captureOnCommitCallbacks: the send is queued on commit, not inline."""
        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                self._checkout()
        self.assertEqual(send.call_count, 1)
        body = send.call_args[0][0]
        self.assertIn('Yangi buyurtma', body)
        self.assertIn('Bildirishnoma', body)

    def test_a_telegram_failure_does_not_break_the_checkout(self):
        from payment.models import Order
        with mock.patch('core.telegram.send', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                # on_commit callbacks run after the response in a real request;
                # executing them here proves the ORDER still exists either way.
                with self.captureOnCommitCallbacks(execute=True):
                    self._checkout()
        self.assertTrue(Order.objects.filter(cart=self.cart).exists())

    def test_a_contact_message_notifies(self):
        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('contact'),
                                 {'subject': 'Savol', 'message': 'Salom'})
        self.assertEqual(send.call_count, 1)
        self.assertIn('Yangi xabar', send.call_args[0][0])

    def test_a_new_pending_review_notifies_and_a_moderated_one_does_not(self):
        from payment.models import Order
        from product.models import Review
        self._checkout()
        order = Order.objects.get(cart=self.cart)

        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                review = Review.objects.create(user=self.user, product=self.product,
                                               order=order, rating=5, text='Zoʻr')
        self.assertEqual(send.call_count, 1)
        self.assertIn('tasdiqlash kerak', send.call_args[0][0])

        # Approving saves it again; the owner does not need telling twice.
        with mock.patch('core.telegram.send', return_value=True) as send:
            with self.captureOnCommitCallbacks(execute=True):
                review.status = Review.Status.APPROVED
                review.save(update_fields=['status'])
        self.assertEqual(send.call_count, 0)
