"""The corrections Kamronbek asked for after using the panel himself.

Ten of them, and they split into three kinds: two lists that had to stop being
code (tag kinds and print methods), screens that were missing an action
(delete, add, a category anywhere), and controls that lied about what they
accept (a price box that took "wqe", an Approve button on an approved review).

The language switcher moving into the header is the only storefront change; it
is one partial now, included in three places, so a test that it is in the
header and gone from the footer is a test of all three.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from core.i18n import tfield
from panel import catalogue, reference
from product import services as product_services
from product.models import (Category, PrintMethod, Product, Review, SizeChart,
                            Tag, TagKind)

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order


class SeededLookupTests(TestCase):
    """Migration 0019 carried every value the code used to hold."""

    def test_the_three_tag_kinds_survived_the_move(self):
        self.assertEqual(
            list(TagKind.objects.values_list('slug', flat=True)),
            ['style', 'theme', 'collection'])

    def test_the_four_print_methods_survived_the_move(self):
        self.assertEqual(
            set(PrintMethod.objects.values_list('slug', flat=True)),
            {'dtf', 'dtg', 'silkscreen', 'embroidery'})

    def test_every_seeded_tag_kept_its_kind(self):
        """The eight tags from Phase 4 still sit on the axes they sat on."""
        by_kind = {}
        for tag in Tag.objects.select_related('kind'):
            by_kind.setdefault(tag.kind.slug if tag.kind_id else None, set()).add(tag.slug)
        self.assertEqual(by_kind.get('style'), {'oversize', 'boxy'})
        self.assertIn('anime', by_kind.get('theme', set()))

    def test_the_names_are_translated_like_every_other_name(self):
        from django.utils import translation
        kind = TagKind.objects.get(slug='style')
        with translation.override('ru'):
            self.assertEqual(tfield(kind, 'name'), 'Стиль')
        with translation.override('en'):
            self.assertEqual(tfield(kind, 'name'), 'Style')


class LookupEditingTests(TestCase):
    """Adding, renaming and removing a kind, a method and a category."""

    def setUp(self):
        self.client.force_login(make_staff('lookups', '+998901260001'))

    def test_a_new_tag_kind_can_be_added_and_used(self):
        response = self.client.post(
            reverse('panel_lookup_new', kwargs={'kind': 'tagkind'}),
            {'name': 'Mavsum', 'name_ru': 'Сезон', 'name_en': 'Season', 'order': '40'})
        self.assertEqual(response.status_code, 302)
        kind = TagKind.objects.get(slug='mavsum')
        self.assertEqual(kind.name_en, 'Season')
        self.assertEqual(kind.order, 40)

        # And a tag can be filed under it straight away.
        self.client.post(reverse('panel_tag_new'),
                         {'name': 'Qish', 'kind': kind.pk})
        self.assertEqual(Tag.objects.get(slug='qish').kind, kind)

    def test_a_new_print_method_can_be_added(self):
        self.client.post(reverse('panel_lookup_new', kwargs={'kind': 'method'}),
                         {'name': 'Sublimatsiya'})
        self.assertTrue(PrintMethod.objects.filter(slug='sublimatsiya').exists())

    def test_a_new_category_can_be_added(self):
        """There was no way to make one at all before — only a select to pick from."""
        self.client.post(reverse('panel_lookup_new', kwargs={'kind': 'category'}),
                         {'name': 'Xudi', 'name_ru': 'Худи'})
        self.assertEqual(Category.objects.get(slug='xudi').name_ru, 'Худи')

    def test_a_fourth_table_cannot_be_reached_through_the_endpoint(self):
        response = self.client.post(
            reverse('panel_lookup_new', kwargs={'kind': 'region'}), {'name': 'X'})
        self.assertEqual(response.status_code, 302)

    def test_a_kind_can_be_renamed_in_place(self):
        kind = TagKind.objects.get(slug='theme')
        self.client.post(
            reverse('panel_reference_inline', kwargs={'kind': 'tagkind', 'pk': kind.pk}),
            {'field': 'name_en', 'value': 'Subject'})
        kind.refresh_from_db()
        self.assertEqual(kind.name_en, 'Subject')

    def test_a_tags_kind_can_be_changed_from_the_row(self):
        tag = Tag.objects.create(slug='oq', name='Oq')
        style = TagKind.objects.get(slug='style')
        self.client.post(
            reverse('panel_reference_inline', kwargs={'kind': 'tag', 'pk': tag.pk}),
            {'field': 'kind', 'value': style.pk})
        tag.refresh_from_db()
        self.assertEqual(tag.kind, style)

    def test_clearing_a_tags_kind_is_allowed(self):
        tag = Tag.objects.create(slug='oq2', name='Oq',
                                 kind=TagKind.objects.get(slug='style'))
        reference.set_field('tag', tag.pk, 'kind', '')
        tag.refresh_from_db()
        self.assertIsNone(tag.kind)


class DeleteTests(TestCase):
    """What may be removed, and what refuses to be."""

    def setUp(self):
        self.client.force_login(make_staff('deleter', '+998901260010'))

    def url(self, kind, pk):
        return reverse('panel_reference_delete', kwargs={'kind': kind, 'pk': pk})

    def test_a_tag_can_be_deleted(self):
        tag = Tag.objects.create(slug='vaqtinchalik', name='Vaqtinchalik')
        response = self.client.post(self.url('tag', tag.pk))
        self.assertTrue(response.json()['ok'])
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_deleting_a_tag_leaves_its_products_alone(self):
        product, _variant = make_product('Teglangan', stock=2)
        tag = Tag.objects.create(slug='oniq', name='Oniq')
        product.tags.add(tag)
        self.client.post(self.url('tag', tag.pk))
        product.refresh_from_db()
        self.assertEqual(product.tags.count(), 0)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_a_tag_kind_with_tags_on_it_refuses(self):
        """PROTECT, so the answer is "something is using this", not a cascade."""
        kind = TagKind.objects.get(slug='theme')
        response = self.client.post(self.url('tagkind', kind.pk))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(TagKind.objects.filter(pk=kind.pk).exists())

    def test_an_empty_tag_kind_can_be_deleted(self):
        kind = TagKind.objects.create(slug='bosh', name='Boʻsh')
        self.assertTrue(self.client.post(self.url('tagkind', kind.pk)).json()['ok'])

    def test_a_print_method_in_use_refuses(self):
        product, _variant = make_product('Bosilgan', stock=2)
        method = PrintMethod.objects.get(slug='dtf')
        product.print_method = method
        product.save(update_fields=['print_method'])
        self.assertEqual(self.client.post(self.url('method', method.pk)).status_code, 400)

    def test_a_category_can_be_deleted_and_its_products_survive(self):
        category = Category.objects.create(name='Vaqtinchalik', slug='vaqt-turkum')
        product, _variant = make_product('Turkumli', stock=2)
        product.category = category
        product.save(update_fields=['category'])

        self.assertTrue(self.client.post(self.url('category', category.pk)).json()['ok'])
        product.refresh_from_db()
        self.assertIsNone(product.category)

    def test_a_chart_can_be_deleted(self):
        chart = SizeChart.objects.create(name='Vaqtinchalik jadval')
        self.assertTrue(self.client.post(self.url('chart', chart.pk)).json()['ok'])


    def test_a_region_cannot_be_deleted_through_this_endpoint(self):
        """An order points at a region; the history of where a parcel went is
        not something a tidy-up gets to remove."""
        from payment.models import Region
        region = Region.objects.first() or Region.objects.create(
            code='9999', name='Sinov', postal_prefix='99')
        response = self.client.post(self.url('region', region.pk))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Region.objects.filter(pk=region.pk).exists())


class BlankNameTests(TestCase):
    """The Uzbek name is the source; clearing it puts a hole on a public page."""

    def setUp(self):
        self.client.force_login(make_staff('names', '+998901260070'))
        self.chart = SizeChart.objects.create(name='Oddiy qolip')

    def test_clearing_the_uzbek_name_is_refused(self):
        with self.assertRaises(ValidationError):
            reference.set_field('chart', self.chart.pk, 'name', '')
        self.chart.refresh_from_db()
        self.assertEqual(self.chart.name, 'Oddiy qolip')

    def test_clearing_a_translation_is_allowed(self):
        """Russian and English fall back to the Uzbek field, so blank is fine."""
        tag = Tag.objects.create(slug='tarjima', name='Tarjima', name_ru='Перевод')
        reference.set_field('tag', tag.pk, 'name_ru', '')
        tag.refresh_from_db()
        self.assertEqual(tag.name_ru, '')

    def test_the_size_guide_renders_no_empty_heading(self):
        """`audit_live` found one: a chart whose name had been cleared."""
        SizeChart.objects.filter(pk=self.chart.pk).update(name='')
        response = self.client.get(reverse('size_guide'))
        if response.status_code == 200:
            self.assertNotIn('<h2 class="h3"></h2>', response.content.decode())


class NumberFieldTests(TestCase):
    """A price box and a stock box only accept numbers, on both sides."""

    def setUp(self):
        self.staff = make_staff('numbers', '+998901260020')
        self.product, self.variant = make_product('Raqamli', stock=5)
        self.client.force_login(self.staff)

    def test_letters_in_a_stock_box_are_refused_rather_than_read_as_zero(self):
        """`_int` turned "sa" into 0, which took the size off sale silently."""
        with self.assertRaises(catalogue.Refused):
            catalogue._count('sa', 'M')

    def test_the_grid_refuses_a_non_numeric_stock(self):
        body = {'name': self.product.name,
                'price_%s' % self.variant.size_id: '100000',
                'stock_%s' % self.variant.size_id: 'sa'}
        with self.assertRaises(catalogue.Refused):
            catalogue.save_grid(self.product, body)

    def test_the_inline_stock_box_refuses_letters(self):
        response = self.client.post(
            reverse('panel_product_inline', kwargs={'slug': self.product.slug}),
            {'field': 'stock', 'value': 'sa', 'size': self.variant.size_id})
        self.assertEqual(response.status_code, 400)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_the_boxes_are_number_inputs(self):
        """A box that accepts letters is a box that refuses the save later."""
        response = self.client.get(
            reverse('panel_product', kwargs={'slug': self.product.slug}))
        self.assertContains(response, 'type="number" inputmode="numeric" min="0" step="1"')


class RefusalKeepsTypingTests(TestCase):
    """One wrong price must not empty a form somebody spent ten minutes on."""

    def setUp(self):
        self.staff = make_staff('typing', '+998901260030')
        _product, self.variant = make_product('Mavjud', stock=2)
        self.client.force_login(self.staff)

    def test_the_refused_values_come_back_on_the_screen(self):
        response = self.client.post(reverse('panel_product_new'), {
            'name': 'Yangi dizayn', 'name_ru': 'Новый дизайн',
            'description': 'Uzun tavsif',
            'price_%s' % self.variant.size_id: 'wqe',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Yangi dizayn')
        self.assertContains(response, 'Новый дизайн')
        self.assertContains(response, 'Uzun tavsif')
        self.assertContains(response, 'wqe')


class ModerationButtonTests(TestCase):
    """Only the decision that would change something is on the card."""

    def setUp(self):
        self.staff = make_staff('mod2', '+998901260040')
        customer = make_user('sharh2', '+998901260041')
        self.product, variant = make_product('Qaror', stock=3)
        order = make_order(customer, variant)
        self.review = product_services.create_review(
            customer, order, self.product, 5, text='Zoʻr')
        self.client.force_login(self.staff)

    def test_a_pending_review_offers_both(self):
        page = self.client.get(reverse('panel_reviews')).content.decode()
        card = page.split('data-review="%d"' % self.review.pk)[1]
        self.assertIn('data-mod="approved"\n', card + '\n')
        self.assertNotIn('data-mod="approved"\n                  hidden', card)

    def test_an_approved_review_does_not_offer_approve(self):
        product_services.moderate(Review.objects.filter(pk=self.review.pk),
                                  Review.Status.APPROVED, by=self.staff)
        page = self.client.get(reverse('panel_reviews'),
                               {'status': 'approved'}).content.decode()
        self.assertIn('data-mod="approved"', page)
        # The one that no longer applies is hidden rather than left out, so the
        # script can swap them when the other decision is made.
        self.assertIn('hidden', page.split('data-mod="approved"')[1][:40])

    def test_a_rejected_review_does_not_offer_reject(self):
        product_services.moderate(Review.objects.filter(pk=self.review.pk),
                                  Review.Status.REJECTED, by=self.staff)
        page = self.client.get(reverse('panel_reviews'),
                               {'status': 'rejected'}).content.decode()
        self.assertIn('hidden', page.split('data-mod="rejected"')[1][:40])


class TagGroupingTests(TestCase):
    """The product form groups its chips, and the shop reads the same rows."""

    def setUp(self):
        self.client.force_login(make_staff('chips', '+998901260050'))

    def test_the_form_groups_chips_under_their_kind(self):
        response = self.client.get(reverse('panel_product_new'))
        groups = {kind.slug if kind else None
                  for kind, tags in response.context['tag_groups']}
        self.assertIn('style', groups)
        self.assertIn('theme', groups)

    def test_a_tag_with_no_kind_still_appears(self):
        Tag.objects.create(slug='yolgiz', name='Yolgʻiz')
        response = self.client.get(reverse('panel_product_new'))
        loose = [tags for kind, tags in response.context['tag_groups'] if kind is None]
        self.assertEqual(len(loose), 1)
        self.assertEqual(loose[0][0].slug, 'yolgiz')

    def test_the_shop_builds_its_filter_groups_from_the_rows(self):
        make_product('Filtrlanadi', stock=2)
        response = self.client.get(reverse('shop'))
        for kind, tags in response.context['tag_groups']:
            self.assertTrue(tags, 'an empty group is a heading over nothing')
            self.assertIsInstance(kind, TagKind)


class LanguagePickerTests(TestCase):
    """It moved out of the footer and into the header.

    Every test here pins the language, and posting to `set_language` is why:
    `LocaleMiddleware` leaves the language it activated active for the rest of
    the process, so a test that switches to Russian hands Russian to whatever
    runs next (§17 #124). `translation.override` puts it back on the way out.
    """

    def setUp(self):
        self.uz = translation.override('uz')
        self.uz.__enter__()
        self.addCleanup(self.uz.__exit__, None, None, None)

    def test_the_header_carries_it(self):
        page = self.client.get(reverse('home')).content.decode()
        head = page.split('</header>')[0]
        self.assertIn('lang--compact', head)
        # Two-letter codes, not "Oʻzbekcha": there is room for six characters
        # beside the cart and the account icon.
        self.assertIn('>uz<', head)
        self.assertIn('>ru<', head)

    def test_the_footer_no_longer_does(self):
        page = self.client.get(reverse('home')).content.decode()
        foot = page.split('<footer')[1]
        self.assertNotIn(reverse('set_language'), foot)

    def test_the_drawer_still_carries_the_full_names(self):
        """The header's copy is hidden on a phone; the drawer is what it uses."""
        page = self.client.get(reverse('home')).content.decode()
        drawer = page.split('id="gx-drawer"')[1].split('</nav>')[0]
        self.assertIn(reverse('set_language'), drawer)
        self.assertIn('Русский', drawer)

    def test_switching_still_lands_on_the_same_page_translated(self):
        """§17 #115: each button posts its own `next`, or only the first works."""
        response = self.client.post(reverse('set_language'),
                                    {'language': 'ru', 'next': '/ru/shop/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/ru/shop/')


class StyleGuideTests(TestCase):
    """Out of the nav, still reachable."""

    def setUp(self):
        self.client.force_login(make_staff('guide', '+998901260060'))

    def test_the_nav_no_longer_links_to_it(self):
        page = self.client.get(reverse('panel_dashboard')).content.decode()
        nav = page.split('<nav class="pnl__nav"')[1].split('</nav>')[0]
        self.assertNotIn('style', nav)

    def test_the_page_still_answers(self):
        self.assertEqual(self.client.get(reverse('style_guide')).status_code, 200)
