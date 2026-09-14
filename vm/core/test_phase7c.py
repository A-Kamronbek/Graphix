"""Phase 7c–7e — the moderation queue, the inbox, and the reference screens.

The queue is the one that matters most: it is why customer photographs are
safe on a public page at all, and approving through it has to move the
product's rating — the exact thing a bulk `update()` silently does not do.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import Msg
from payment.models import DeliveryOption, District, Region
from product import services as product_services
from product.models import Product, Review, SizeChart, Tag

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order


class ModerationTests(TestCase):
    """Approve or reject, and the product's rating moves with it."""

    def setUp(self):
        self.staff = make_staff('moderator', '+998901240001')
        self.customer = make_user('yozgan', '+998901240002')
        self.product, self.variant = make_product('Navbat', stock=4)
        order = make_order(self.customer, self.variant)
        self.review = product_services.create_review(
            self.customer, order, self.product, 5, text='Zoʻr')
        self.client.force_login(self.staff)

    def url(self):
        return reverse('panel_review_moderate', kwargs={'pk': self.review.pk})

    def test_the_queue_shows_what_is_waiting(self):
        response = self.client.get(reverse('panel_reviews'))
        self.assertContains(response, 'Zoʻr')
        self.assertEqual(response.context['pending'], 1)

    def test_approving_publishes_it_and_moves_the_rating(self):
        """A bulk update fires no signals; that is what this goes through a service for."""
        body = self.client.post(self.url(), {'status': 'approved'}).json()
        self.assertTrue(body['ok'])
        self.review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.review.status, 'approved')
        self.assertEqual(self.product.review_count, 1)
        self.assertEqual(self.product.rating_avg, Decimal('5.0'))
        self.assertEqual(body['rating'], '5.0')

    def test_rejecting_leaves_the_rating_where_it_was(self):
        self.client.post(self.url(), {'status': 'rejected'})
        self.product.refresh_from_db()
        self.assertEqual(self.product.review_count, 0)

    def test_the_decision_is_recorded_against_whoever_made_it(self):
        self.client.post(self.url(), {'status': 'approved'})
        self.review.refresh_from_db()
        self.assertEqual(self.review.moderated_by, self.staff)
        self.assertIsNotNone(self.review.moderated_at)

    def test_an_invented_decision_is_refused(self):
        response = self.client.post(self.url(), {'status': 'maybe'})
        self.assertEqual(response.status_code, 400)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'pending')

    def test_a_customer_cannot_moderate(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(self.url(), {'status': 'approved'}).status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, 'pending')

    def test_the_photographs_are_not_shown_as_thumbnails(self):
        """A moderation queue with 72 px images is one where everything is approved."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css' / 'panel.css'
               ).read_text(encoding='utf-8')
        self.assertIn('.mod__pics img', css)
        self.assertIn('min(260px, 62vw)', css)


class InboxTests(TestCase):
    """The contact form's inbox."""

    def setUp(self):
        self.staff = make_staff('qabul', '+998901240003')
        self.customer = make_user('yozuvchi7', '+998901240004')
        self.msg = Msg.objects.create(user=self.customer, phone_num='+998 90 124 00 04',
                                      topic='Savol', msg_text='Qachon yetkaziladi?')
        self.client.force_login(self.staff)

    def test_the_inbox_lists_messages_and_counts_the_unread(self):
        response = self.client.get(reverse('panel_messages'))
        self.assertContains(response, 'Qachon yetkaziladi?')
        self.assertEqual(response.context['unread'], 1)

    def test_the_number_is_tappable(self):
        """The first thing somebody does with a message is ring back.

        Unspaced in the href, grouped on screen: a ``tel:`` URI with spaces in
        it is one some Android dialers refuse to open.
        """
        response = self.client.get(reverse('panel_messages'))
        self.assertContains(response, 'tel:+998901240004')
        self.assertContains(response, '+998 90 124 00 04')

    def test_marking_read_and_unread_both_work(self):
        url = reverse('panel_message_read', kwargs={'pk': self.msg.pk})
        self.assertTrue(self.client.post(url, {'value': '1'}).json()['value'])
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_read)

        # Back again, because people misclick.
        self.assertFalse(self.client.post(url, {'value': '0'}).json()['value'])
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_read)

    def test_the_unread_filter_narrows_the_list(self):
        Msg.objects.create(user=self.customer, phone_num='x', topic='Oʻqilgan',
                           msg_text='...', is_read=True)
        response = self.client.get(reverse('panel_messages'), {'show': 'unread'})
        self.assertEqual(response.context['total'], 1)

    def test_a_customer_cannot_read_the_inbox(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('panel_messages')).status_code, 403)


class ReferenceTests(TestCase):
    """Editing the small tables — and, more importantly, not editing the rest.

    One endpoint serves five models, which is only safe because of the
    allowlist in `panel/reference.py`. These tests are mostly about what it
    refuses.
    """

    def setUp(self):
        self.staff = make_staff('sozlovchi', '+998901240005')
        self.client.force_login(self.staff)
        self.region = Region.objects.create(code='9999', name='Sinov viloyati',
                                            postal_prefix='99')
        self.district = District.objects.create(region=self.region, code='999901',
                                                name='Sinov tumani')
        self.tier = DeliveryOption.objects.create(code='sinov', name='Sinov',
                                                  price=Decimal('30000'))
        self.tag = Tag.objects.create(slug='sinov-teg', name='Sinov teg')

    def url(self, kind, pk):
        return reverse('panel_reference_inline', kwargs={'kind': kind, 'pk': pk})

    def test_a_district_can_be_renamed_without_a_deploy(self):
        self.client.post(self.url('district', self.district.pk),
                         {'field': 'name', 'value': 'Yangi nom'})
        self.district.refresh_from_db()
        self.assertEqual(self.district.name, 'Yangi nom')

    def test_a_postal_prefix_can_be_corrected(self):
        self.client.post(self.url('region', self.region.pk),
                         {'field': 'postal_prefix', 'value': '100'})
        self.region.refresh_from_db()
        self.assertEqual(self.region.postal_prefix, '100')

    def test_a_prefix_that_is_not_two_or_three_digits_is_refused(self):
        """It is what decides whether a customer's typed index is accepted."""
        for bad in ('1', '1234', 'ab'):
            with self.subTest(bad=bad):
                response = self.client.post(self.url('region', self.region.pk),
                                            {'field': 'postal_prefix', 'value': bad})
                self.assertEqual(response.status_code, 400)
        self.region.refresh_from_db()
        self.assertEqual(self.region.postal_prefix, '99')

    def test_an_empty_prefix_is_allowed_because_it_is_the_escape(self):
        """A region with no prefix accepts any index, and that is deliberate."""
        self.client.post(self.url('region', self.region.pk),
                         {'field': 'postal_prefix', 'value': ''})
        self.region.refresh_from_db()
        self.assertEqual(self.region.postal_prefix, '')

    def test_the_soato_code_cannot_be_edited(self):
        """It ties the row to the classifier it came from."""
        response = self.client.post(self.url('region', self.region.pk),
                                    {'field': 'code', 'value': '0000'})
        self.assertEqual(response.status_code, 400)
        self.region.refresh_from_db()
        self.assertEqual(self.region.code, '9999')

    def test_a_delivery_price_can_be_changed(self):
        self.client.post(self.url('delivery', self.tier.pk),
                         {'field': 'price', 'value': '45 000'})
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.price, Decimal('45000'))

    def test_a_negative_delivery_price_is_refused(self):
        response = self.client.post(self.url('delivery', self.tier.pk),
                                    {'field': 'price', 'value': '-1'})
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_table_is_refused(self):
        self.assertEqual(self.client.post(self.url('order', 1),
                                          {'field': 'status', 'value': 'done'}).status_code,
                         400)

    def test_a_tag_is_renamed_in_all_three_languages(self):
        for field, value in (('name', 'Uz'), ('name_ru', 'Ru'), ('name_en', 'En')):
            self.client.post(self.url('tag', self.tag.pk),
                             {'field': field, 'value': value})
        self.tag.refresh_from_db()
        self.assertEqual((self.tag.name, self.tag.name_ru, self.tag.name_en),
                         ('Uz', 'Ru', 'En'))

    def test_a_new_tag_gets_a_slug_without_anyone_typing_one(self):
        self.client.post(reverse('panel_tag_new'),
                         {'name': 'Yangi Kolleksiya', 'kind': 'collection'})
        tag = Tag.objects.get(name='Yangi Kolleksiya')
        self.assertEqual(tag.slug, 'yangi-kolleksiya')
        self.assertEqual(tag.kind, 'collection')

    def test_two_tags_with_the_same_name_get_different_slugs(self):
        self.client.post(reverse('panel_tag_new'), {'name': 'Takror'})
        self.client.post(reverse('panel_tag_new'), {'name': 'Takror'})
        self.assertEqual(Tag.objects.filter(name='Takror').count(), 2)
        self.assertEqual(Tag.objects.filter(slug='takror-2').count(), 1)

    def test_the_screens_are_guarded(self):
        self.client.force_login(make_user('begona7', '+998901240006'))
        for name in ('panel_settings', 'panel_regions'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_the_regions_screen_searches_districts(self):
        District.objects.create(region=self.region, code='999902', name='Boshqa tuman')
        response = self.client.get(reverse('panel_regions'), {'q': 'Boshqa'})
        found = [d.name for r in response.context['regions'] for d in r.districts.all()]
        self.assertEqual(found, ['Boshqa tuman'])
