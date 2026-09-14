"""Four more corrections Kamronbek found by using the settings screen.

Three of them take something away, which is the kind of change a test suite is
worst at holding: nothing fails when a field quietly comes back.

* **Tartib is gone** (§17 #171) — the sort-order box on tag kinds and print
  methods. Four rows in each table; a number somebody has to invent before they
  can add a print method is a decision that buys nothing. Both read oldest
  first now.
* **Qolip is gone** (§17 #172) — ``Product.fit`` and ``SizeChart.fit``, two
  fixed cuts. A cut is something the owner wants to *say* about a garment and a
  tag says it already. A size chart is now a name and a picture.
* **The tag list has a search**, for the reason the product form's chips have
  one: the owner writes the tags, so the list only grows.
* **Tag kinds and tags are two sections**, so the second heading has room to
  breathe and the tab that says Teglar goes to the tags.

The assertions are mostly "this is not on the page" and "this field does not
exist", deliberately: that is the shape of the regression.
"""
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from panel import reference
from product.models import PrintMethod, Product, SizeChart, Tag, TagKind

from .test_phase4 import make_product
from .test_phase7 import make_staff
from .test_phase7b import photo


class TartibIsGoneTests(TestCase):
    """The sort-order column, and every box that wrote to it."""

    def setUp(self):
        self.client.force_login(make_staff('tartib', '+998901270001'))

    def test_neither_lookup_table_has_an_order_column_any_more(self):
        for model in (TagKind, PrintMethod):
            with self.subTest(model=model.__name__):
                self.assertNotIn('order', [f.name for f in model._meta.get_fields()])

    def test_both_tables_read_oldest_first(self):
        for model in (TagKind, PrintMethod):
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.ordering, ['id'])
                ids = list(model.objects.values_list('pk', flat=True))
                self.assertEqual(ids, sorted(ids))

    def test_a_newly_added_kind_lands_at_the_end(self):
        self.client.post(reverse('panel_lookup_new', kwargs={'kind': 'tagkind'}),
                         {'name': 'Mavsum'})
        self.assertEqual(TagKind.objects.last().slug, 'mavsum')

    def test_the_settings_screen_no_longer_shows_a_tartib_box(self):
        page = self.client.get(reverse('panel_settings')).content.decode()
        self.assertNotIn('data-ref-field="order"', page)
        self.assertNotIn('Tartib<', page)

    def test_order_cannot_be_written_through_the_reference_endpoint(self):
        """It is not in the allowlist, so it is refused rather than ignored."""
        kind = TagKind.objects.first()
        with self.assertRaises(ValidationError):
            reference.set_field('tagkind', kind.pk, 'order', '5')

    def test_a_posted_order_is_simply_not_read(self):
        """An old form, or a curious person: the row is created and nothing breaks."""
        response = self.client.post(
            reverse('panel_lookup_new', kwargs={'kind': 'method'}),
            {'name': 'Sublimatsiya', 'order': '70'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PrintMethod.objects.filter(slug='sublimatsiya').exists())


class QolipIsGoneTests(TestCase):
    """The cut, and the size-chart column that keyed on it."""

    def setUp(self):
        self.client.force_login(make_staff('qolip', '+998901270002'))

    def test_the_field_is_off_both_models(self):
        for model in (Product, SizeChart):
            with self.subTest(model=model.__name__):
                self.assertNotIn('fit', [f.name for f in model._meta.get_fields()])

    def test_the_product_class_no_longer_carries_the_choices(self):
        self.assertFalse(hasattr(Product, 'Fit'))

    def test_the_product_form_has_no_qolip_select(self):
        page = self.client.get(reverse('panel_product_new')).content.decode()
        self.assertNotIn('name="fit"', page)
        self.assertNotIn('id="p-fit"', page)

    def test_the_settings_screen_has_no_qolip_select(self):
        page = self.client.get(reverse('panel_settings')).content.decode()
        self.assertNotIn('data-ref-field="fit"', page)
        self.assertNotIn('name="fit"', page)

    def test_fit_cannot_be_written_onto_a_chart(self):
        chart = SizeChart.objects.create(name='Sinov jadvali')
        with self.assertRaises(ValidationError):
            reference.set_field('chart', chart.pk, 'fit', 'oversize')

    def test_the_spec_strip_on_the_product_page_has_no_qolip_row(self):
        product, _ = make_product('Xususiyatlar', gsm=200, material='100% paxta')
        page = self.client.get(
            reverse('item', kwargs={'slug': product.slug})).content.decode()
        self.assertIn('Zichlik', page, 'the spec strip should still be there')
        self.assertNotIn('Qolip', page)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_a_chart_is_created_from_a_name_and_a_picture_alone(self):
        response = self.client.post(reverse('panel_chart_new'), {
            'name': 'Yangi jadval',
            # Posted by nothing on the screen; proves an old form cannot revive it.
            'fit': 'oversize',
            'image': SimpleUploadedFile('chart.jpg', photo().read(),
                                        content_type='image/jpeg'),
        })
        self.assertEqual(response.status_code, 302)
        chart = SizeChart.objects.get(name='Yangi jadval')
        self.assertTrue(chart.image)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_a_chart_still_needs_both(self):
        before = SizeChart.objects.count()
        self.client.post(reverse('panel_chart_new'), {'name': 'Rasmsiz'})
        self.assertEqual(SizeChart.objects.count(), before)


class TagSearchTests(TestCase):
    """The tag list is filtered by typing, in every language it is written in."""

    def setUp(self):
        self.client.force_login(make_staff('qidiruv', '+998901270003'))
        self.page = self.client.get(reverse('panel_settings')).content.decode()

    def test_the_settings_screen_carries_a_search_over_the_tag_list(self):
        self.assertIn('data-rowsearch', self.page)
        self.assertIn('data-rowsearch-input', self.page)
        self.assertIn('data-rowsearch-empty', self.page)

    def test_every_tag_row_carries_a_haystack(self):
        rows = self.page.count('data-rowsearch-row')
        self.assertEqual(rows, Tag.objects.count())

    def test_the_haystack_holds_all_three_languages_and_the_kind(self):
        """The tag somebody remembers may well be the Russian one."""
        tag = Tag.objects.select_related('kind').exclude(name_ru='').first()
        self.assertIsNotNone(tag, 'the seeded tags should carry Russian names')
        needle = 'data-search="%s %s %s %s"' % (
            tag.name, tag.name_ru, tag.name_en, tag.kind.name if tag.kind_id else '')
        self.assertIn(needle, self.page)


class SettingsSectionTests(TestCase):
    """Tag kinds and tags are two sections, not one heading followed by another."""

    def setUp(self):
        self.client.force_login(make_staff('boblar', '+998901270004'))
        self.page = self.client.get(reverse('panel_settings')).content.decode()

    def test_each_has_its_own_section_and_anchor(self):
        self.assertIn('id="teg-turlari"', self.page)
        self.assertIn('id="teglar"', self.page)

    def test_the_tabs_reach_both(self):
        self.assertIn('href="#teg-turlari"', self.page)
        self.assertIn('href="#teglar"', self.page)
