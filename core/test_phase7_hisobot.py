"""Kamronbek's fifth pass over the panel and the account screens.

Five changes, and only one of them is logic:

* **The "I can't remember my password" button signs you out**, and now says so
  before it is pressed (§17 #176).
* **Sign in and sign up are one centred column**, like every other screen in
  the flow, instead of a form pushed to the left of a brand mark (§17 #177).
* **The dashboard is Hisobot, not Bugun**, and three of its tiles are renamed
  to the words the owner uses (§17 #178).
* **"Running low" has one definition**, on the model, shared by the tile, the
  list under it and the list it links to (§17 #179).
* **A size pill is red, amber or plain**, and red wins (§17 #180).

The low-stock rules are the part worth holding hardest: every one of them is a
row that either does or does not appear on the first screen the owner sees each
morning, and a list that fills up with sizes nobody can buy is a list he stops
reading.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from product.models import LOW_STOCK, Colour, Product, Size, Variant

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff


def sized(product, label, stock, *, available=True, price='150000'):
    """Give ``product`` one more size, with its own stock and switch."""
    return Variant.objects.create(
        product=product,
        size=Size.objects.create(size=label),
        colour=Colour.objects.get_or_create(colour='Standart')[0],
        price=Decimal(price), available=available, stock=stock,
    )


class ForgotPasswordWarningTests(TestCase):
    """The escape hatch logs you out; the screen has to say so first."""

    def setUp(self):
        self.user = make_user('unutgan', '+998901280001')
        self.client.force_login(self.user)

    def test_the_settings_page_warns_before_the_button_is_pressed(self):
        page = self.client.get(reverse('account_settings')).content.decode()
        self.assertIn('Joriy parolni eslay olmayapman', page)
        self.assertIn('hisobingizdan chiqaradi', page)

    def test_and_the_button_really_does_sign_you_out(self):
        """The warning has to be true, so this asserts the behaviour as well."""
        response = self.client.post(reverse('account_forgot_password'))
        self.assertRedirects(response, reverse('password_reset_request'))
        self.assertNotIn('_auth_user_id', self.client.session)


class AuthLayoutTests(TestCase):
    """Sign in and sign up are the same centred column as the rest of the flow."""

    def test_neither_screen_carries_the_brand_mark_beside_the_form(self):
        for name in ('login', 'signup'):
            with self.subTest(screen=name):
                page = self.client.get(reverse(name)).content.decode()
                self.assertNotIn('auth__art', page)

    def test_both_use_the_narrow_centred_shell(self):
        for name in ('login', 'signup'):
            with self.subTest(screen=name):
                page = self.client.get(reverse(name)).content.decode()
                self.assertIn('auth auth--narrow', page)

    def test_the_otp_screen_they_were_matched_to_is_unchanged(self):
        """The shape came from somewhere; that somewhere still has it."""
        page = self.client.get(reverse('password_reset_request')).content.decode()
        self.assertIn('auth auth--narrow', page)


class DashboardWordingTests(TestCase):
    """Hisobot, and the three tiles Kamronbek renamed."""

    def setUp(self):
        self.client.force_login(make_staff('hisobot', '+998901280002'))
        self.page = self.client.get(reverse('panel_dashboard')).content.decode()

    def test_the_tab_and_the_heading_say_hisobot(self):
        self.assertIn('Hisobot', self.page)
        self.assertNotIn('>Bugun<', self.page)

    def test_the_renamed_tiles(self):
        for label in ('Jarayonda', 'Yetkazilmoqda', 'Yangi sharhlar'):
            with self.subTest(label=label):
                self.assertIn(label, self.page)
        for gone in ('Yigʻiladi', 'Sharhlar navbatda'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.page)

    def test_bugungi_buyurtmalar_is_still_about_today(self):
        """Renaming the page did not rename the tiles that really are daily."""
        self.assertIn('Bugungi buyurtmalar', self.page)


class RunningLowTests(TestCase):
    """What belongs on the "Zaxira tugayapti" list, and what does not."""

    def setUp(self):
        self.product, self.first = make_product('Zaxira sinovi', stock=2)

    def test_the_threshold_is_five_and_five_counts(self):
        self.assertEqual(LOW_STOCK, 5)
        self.first.stock = LOW_STOCK
        self.first.save(update_fields=['stock'])
        self.assertIn(self.first, Variant.objects.running_low())

    def test_six_does_not_count(self):
        self.first.stock = LOW_STOCK + 1
        self.first.save(update_fields=['stock'])
        self.assertNotIn(self.first, Variant.objects.running_low())

    def test_nothing_left_still_counts(self):
        """A size on sale with zero behind it is the most urgent row, not an excluded one."""
        self.first.stock = 0
        self.first.save(update_fields=['stock'])
        self.assertIn(self.first, Variant.objects.running_low())

    def test_a_size_taken_off_sale_does_not_count(self):
        off = sized(self.product, 'XL-off', 1, available=False)
        self.assertNotIn(off, Variant.objects.running_low())

    def test_nothing_on_a_withdrawn_product_counts(self):
        """An old design nobody sells should not fill the morning's list."""
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        self.assertEqual(Variant.objects.running_low().count(), 0)

    def test_kamronbeks_own_example(self):
        """S 0 on sale, M 2 on sale, L 10 on sale, XL 1 off sale -> S and M only."""
        product, small = make_product('Namuna', stock=0)
        medium = sized(product, 'M-namuna', 2)
        sized(product, 'L-namuna', 10)
        sized(product, 'XL-namuna', 1, available=False)
        low = set(Variant.objects.running_low().filter(product=product))
        self.assertEqual(low, {small, medium})


class LowStockScreenTests(TestCase):
    """The tile, the list under it and the list it opens all say the same thing."""

    def setUp(self):
        self.client.force_login(make_staff('zaxira', '+998901280003'))
        self.product, self.small = make_product('Sanaladigan', stock=1)
        self.hidden = sized(self.product, 'XL-hidden', 1, available=False)
        self.stocked, _ = make_product('Sanalmaydigan', stock=40)

    def test_the_tile_counts_only_what_is_on_sale(self):
        page = self.client.get(reverse('panel_dashboard'))
        self.assertEqual(page.context['low_stock_count'], 1)
        self.assertEqual(list(page.context['low_stock']), [self.small])

    def test_the_list_behind_the_tile_shows_exactly_those_products(self):
        """§17 #155's defect in miniature: a tile that promises a number its link
        does not show."""
        page = self.client.get(reverse('panel_products'), {'low': '1'})
        self.assertEqual(list(page.context['products']), [self.product])

    def test_a_product_whose_only_low_size_is_off_sale_is_not_listed(self):
        Variant.objects.filter(pk=self.small.pk).update(stock=40)
        page = self.client.get(reverse('panel_products'), {'low': '1'})
        self.assertEqual(list(page.context['products']), [])

    def test_a_product_appears_once_even_with_two_low_sizes(self):
        """The old join needed `.distinct()` to avoid saying it twice."""
        sized(self.product, 'M-ham', 2)
        page = self.client.get(reverse('panel_products'), {'low': '1'})
        self.assertEqual(list(page.context['products']), [self.product])


class SizePillTests(TestCase):
    """Red for a size nobody can buy, amber for one nearly gone, red when both."""

    def setUp(self):
        self.client.force_login(make_staff('pillar', '+998901280004'))

    def pill(self, variant):
        """The class list of that variant's box on the products list."""
        page = self.client.get(reverse('panel_products')).content.decode()
        needle = 'data-size="%d"' % variant.size_id
        before = page[:page.index(needle)]
        return before[before.rindex('<label class="stockbox'):]

    def test_plenty_left_is_plain(self):
        _, variant = make_product('Toʻla', stock=40)
        classes = self.pill(variant)
        self.assertNotIn('is-out', classes)
        self.assertNotIn('is-low', classes)

    def test_nearly_gone_is_amber(self):
        _, variant = make_product('Kam qoldi', stock=3)
        self.assertIn('is-low', self.pill(variant))

    def test_nothing_left_is_red_not_amber(self):
        _, variant = make_product('Tugadi', stock=0)
        classes = self.pill(variant)
        self.assertIn('is-out', classes)
        self.assertNotIn('is-low', classes)

    def test_off_sale_with_stock_left_is_red(self):
        _, variant = make_product('Sotuvdan olingan', stock=3, available=False)
        classes = self.pill(variant)
        self.assertIn('is-out', classes)
        self.assertNotIn('is-low', classes)

    def test_the_property_the_pill_reads(self):
        _, variant = make_product('Xossalar', stock=3)
        self.assertTrue(variant.is_running_low)
        variant.stock = 0
        self.assertFalse(variant.is_running_low, 'zero is red, not amber')
        variant.stock = 3
        variant.available = False
        self.assertFalse(variant.is_running_low, 'off sale is red, not amber')

    def test_the_inline_save_answers_with_both_facts(self):
        """So the pill recolours as the number is typed, without a page load."""
        product, variant = make_product('Tezkor', stock=40)
        answer = self.client.post(
            reverse('panel_product_inline', kwargs={'slug': product.slug}),
            {'field': 'stock', 'value': '2', 'size': variant.size_id}).json()
        self.assertEqual(answer, {'ok': True, 'value': 2,
                                  'purchasable': True, 'low': True})

        answer = self.client.post(
            reverse('panel_product_inline', kwargs={'slug': product.slug}),
            {'field': 'stock', 'value': '0', 'size': variant.size_id}).json()
        self.assertEqual(answer, {'ok': True, 'value': 0,
                                  'purchasable': False, 'low': False})
