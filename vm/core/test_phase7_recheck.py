"""What the Phase 7 recheck found, one test per defect.

These are all things the phase's own 91 tests passed over, and the split is
worth recording: most of them could not be caught by a test as the suite was
written, because they were in the browser, in a stylesheet, or in a query
string nobody had sent. What CAN be pinned down in Django's test client is
pinned down here, so none of them comes back.

Two of the findings have no test in this file and cannot have one:

* the status control saving nothing (`panel.js` built its form data after
  disabling the select, so the POST carried no `status` at all) — a defect in
  a browser, found by driving one, guarded by `.git/recheck_p7.py`;
* the panel being unreachable for a staff account whose phone was never
  verified — raised with Kamronbek rather than changed here, because it is the
  OTP middleware and §4 says auth is not changed alone.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from cart.models import CartItem
from core.models import Msg
from panel import catalogue, reference
from payment.models import DeliveryOption, Order, Region
from product import services as product_services
from product.models import Product, Review, Size, Tag, TagKind

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order


def make_paid_order(user, name='Buyum'):
    """A paid order with one line on it, for the screens that read one."""
    _product, variant = make_product(name, stock=5)
    return make_order(user, variant, status='paid')


class QueryStringTests(TestCase):
    """Nothing a person can type into the address bar should be a 500."""

    def setUp(self):
        self.staff = make_staff('qs', '+998901250001')
        self.client.force_login(self.staff)

    def test_a_malformed_date_filters_nothing_instead_of_crashing(self):
        """An unparseable date reached the query compiler and raised there.

        A bookmark with a half-typed date in it, or a link somebody edited, was
        answered with a 500 rather than with the list.
        """
        for bad in ('abc', '2026-13-45', '14/09/2026', '2026-09-'):
            with self.subTest(bad=bad):
                response = self.client.get(reverse('panel_orders'), {'since': bad})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['filters']['since'], '')

    def test_a_real_date_still_filters(self):
        response = self.client.get(reverse('panel_orders'), {'since': '2026-01-01'})
        self.assertEqual(response.context['filters']['since'], '2026-01-01')

    def test_two_statuses_at_once(self):
        """The dashboard's "to pack" tile counts `paid` and `processing`.

        It used to link to `paid` alone, so the number on the tile and the
        number of rows in the list it opened were different.
        """
        response = self.client.get(reverse('panel_orders'),
                                   {'status': 'paid,processing'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['chosen_statuses']),
                         {'paid', 'processing'})

    def test_a_nonsense_status_is_ignored_rather_than_obeyed(self):
        response = self.client.get(reverse('panel_orders'), {'status': 'nonsense'})
        self.assertEqual(response.context['chosen_statuses'], [])

    def test_the_dashboards_to_pack_tile_and_its_link_agree(self):
        """The tile's number and the list behind it count the same orders."""
        paid = make_paid_order(make_user('packer', '+998901250002'))
        paid.status = Order.Status.PROCESSING
        paid.save(update_fields=['status'])

        tile = self.client.get(reverse('panel_dashboard')).context['to_pack']
        listed = self.client.get(reverse('panel_orders'),
                                 {'status': 'paid,processing'}).context['total']
        self.assertEqual(tile, listed)

    def test_the_low_stock_tile_lands_on_the_low_stock_products(self):
        product, variant = make_product('Kam qolgan', stock=2)
        response = self.client.get(reverse('panel_products'), {'low': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(product, list(response.context['products']))

        variant.stock = 500
        variant.save(update_fields=['stock'])
        again = self.client.get(reverse('panel_products'), {'low': '1'})
        self.assertNotIn(product, list(again.context['products']))


class SafeRedirectTests(TestCase):
    """`next` arrives in a POST body and is not somewhere to send a browser."""

    def setUp(self):
        self.staff = make_staff('redir', '+998901250010')
        self.order = make_paid_order(make_user('mijoz', '+998901250011'))
        self.client.force_login(self.staff)

    def url(self):
        return reverse('panel_order_status',
                       kwargs={'order_no': self.order.order_no})

    def test_an_off_site_next_is_refused(self):
        response = self.client.post(self.url(), {'status': 'processing',
                                                 'next': 'https://example.com/'})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('example.com', response['Location'])

    def test_a_path_on_this_site_is_honoured(self):
        response = self.client.post(self.url(),
                                    {'status': 'processing',
                                     'next': '/uz/boshqaruv/buyurtmalar/'})
        self.assertEqual(response['Location'], '/uz/boshqaruv/buyurtmalar/')


class NeverCacheTests(TestCase):
    """Panel pages carry customers' names, numbers and addresses."""

    def setUp(self):
        self.client.force_login(make_staff('cache', '+998901250020'))

    def test_the_panel_is_not_cacheable(self):
        for name in ('panel_dashboard', 'panel_orders', 'panel_products',
                     'panel_reviews', 'panel_messages', 'panel_settings'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertIn('no-store', response['Cache-Control'])


class ReferenceLengthTests(TestCase):
    """A value longer than its column was a 500, not a sentence."""

    def setUp(self):
        self.staff = make_staff('ref', '+998901250030')
        self.tag = Tag.objects.create(slug='rechek', name='Rechek',
                                      kind=TagKind.objects.get(slug='theme'))
        self.client.force_login(self.staff)

    def test_the_service_refuses_it(self):
        with self.assertRaises(ValidationError):
            reference.set_field('tag', self.tag.pk, 'name', 'x' * 200)

    def test_the_endpoint_answers_400_not_500(self):
        response = self.client.post(
            reverse('panel_reference_inline',
                    kwargs={'kind': 'tag', 'pk': self.tag.pk}),
            {'field': 'name', 'value': 'x' * 200})
        self.assertEqual(response.status_code, 400)
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, 'Rechek')

    def test_a_value_that_fits_still_saves(self):
        self.assertEqual(reference.set_field('tag', self.tag.pk, 'name', 'Yangi'),
                         'Yangi')

    def test_a_price_rounds_half_up_like_the_rest_of_the_project(self):
        tier = DeliveryOption.objects.create(code='rechek', name='Rechek',
                                             price=Decimal('1000'))
        self.assertEqual(reference.set_field('delivery', tier.pk, 'price', '2500.5'),
                         Decimal('2501'))


class ProductLengthTests(TestCase):
    """The same rule on the product form, which has the same shape."""

    def test_an_over_long_name_is_refused_with_a_sentence(self):
        with self.assertRaises(catalogue.Refused):
            catalogue.save_product({'name': 'x' * 300})

    def test_a_price_rounds_half_up(self):
        self.assertEqual(catalogue.price_of('2500.5'), Decimal('2501'))


class OrderArithmeticTests(TestCase):
    """The numbers on an order have to add up on the screen."""

    def setUp(self):
        self.staff = make_staff('sums', '+998901250040')
        self.customer = make_user('haridor', '+998901250041')
        self.order = make_paid_order(self.customer)
        self.client.force_login(self.staff)

    def test_each_line_shows_its_own_total_not_the_price_of_one(self):
        """`price_stat` is the unit price; the order's total is price x qty.

        The page printed the unit price beside "x 2" and the total below, so
        three numbers on screen did not add up and nothing a staff member could
        do with them would make them.
        """
        item = self.order.cart.cart_items.first()
        item.quantity = 3
        item.save(update_fields=['quantity'])

        response = self.client.get(reverse('panel_order',
                                           kwargs={'order_no': self.order.order_no}))
        line = response.context['items'][0]
        self.assertEqual(line.line_total, item.price_stat * 3)


class ModerationLabelTests(TestCase):
    """The badge says what the review IS; the button says what you are doing."""

    def setUp(self):
        self.staff = make_staff('labels', '+998901250050')
        self.customer = make_user('sharhchi', '+998901250051')
        self.product, self.variant = make_product('Yorliq', stock=3)
        order = make_order(self.customer, self.variant)
        self.review = product_services.create_review(
            self.customer, order, self.product, 4, text='Yaxshi')
        self.client.force_login(self.staff)

    def test_the_response_carries_the_state_label_and_a_rendered_rating(self):
        """The script had been copying the button's own text into the badge.

        So approving a review left it reading "Tasdiqlash" — approve — where
        "Tasdiqlangan" belongs, and the rating line lost its unit because the
        script was assembling that sentence too.
        """
        data = self.client.post(
            reverse('panel_review_moderate', kwargs={'pk': self.review.pk}),
            {'status': Review.Status.APPROVED}).json()

        self.assertTrue(data['ok'])
        self.assertEqual(data['label'], str(Review.Status.APPROVED.label))
        self.assertNotEqual(data['label'], 'Tasdiqlash')
        self.assertIn('ta', data['rating_line'])
        self.assertIn(str(data['count']), data['rating_line'])


class SizeOrderTests(TestCase):
    """The grid on the most important screen must not come back shuffled."""

    def test_sizes_have_an_ordering(self):
        """`Size.objects.all()` had none, and the grid is built from it.

        Postgres may return an unordered scan in any order, and it moves a row
        it has updated, so the size grid was one edit away from S, XL, M, L.
        """
        self.assertEqual(Size._meta.ordering, ['id'])

    def test_the_form_lists_them_in_that_order(self):
        self.client.force_login(make_staff('sizes', '+998901250060'))
        response = self.client.get(reverse('panel_product_new'))
        rows = [row['size'].pk for row in response.context['grid']]
        self.assertEqual(rows, sorted(rows))


class MarkupTests(TestCase):
    """Three things the panel's own audit found the first time it was run."""

    def setUp(self):
        self.staff = make_staff('markup', '+998901250070')
        make_product('Koʻrinish', stock=5)
        self.client.force_login(self.staff)

    def test_the_thumbnail_link_is_not_a_second_unnamed_link(self):
        """It goes where the name beside it goes and holds an empty-alt image,
        so to a screen reader it was a link with no name at all."""
        response = self.client.get(reverse('panel_products'))
        self.assertContains(response, 'class="prod__pic"')
        self.assertContains(response, 'aria-hidden="true" tabindex="-1"')

    def test_the_new_tag_form_has_labels_rather_than_placeholders(self):
        """A placeholder is gone the moment somebody types in the box."""
        response = self.client.get(reverse('panel_settings'))
        self.assertNotContains(response, 'placeholder="Nomi (uz)"')
        self.assertContains(response, '>Nomi (uz)<')

    def test_the_chart_upload_is_named(self):
        """It was the one control on the panel with no label of any kind.

        It is now a visually-hidden input driven by a styled `<label for=…>`,
        which is also what keeps the browser's own English "Choose File" off an
        Uzbek screen — so the assertion is that the label points at it.
        """
        response = self.client.get(reverse('panel_settings'))
        self.assertContains(response, 'name="image"')
        self.assertContains(response, 'for="chart-image"')
        self.assertContains(response, '>Rasm<')


class UnreadCountTests(TestCase):
    """The inbox already computed this and then threw it away."""

    def setUp(self):
        self.staff = make_staff('inbox', '+998901250080')
        self.msg = Msg.objects.create(user=self.staff, phone_num='+998 90 125 00 80',
                                      topic='Savol', msg_text='Qachon?')
        self.client.force_login(self.staff)

    def test_marking_read_returns_the_new_count(self):
        data = self.client.post(
            reverse('panel_message_read', kwargs={'pk': self.msg.pk}),
            {'value': '1'}).json()
        self.assertEqual(data['unread'], 0)

    def test_the_header_count_is_the_element_the_script_updates(self):
        response = self.client.get(reverse('panel_messages'))
        self.assertContains(response, 'data-unread-count')
