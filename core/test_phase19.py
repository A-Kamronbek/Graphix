"""Phase 19: the owner's second round of changes, and three faults found with them.

The owner asked for a white page, for the heart on a card to stop filling its
whole button, for the bar fixed to the foot of the product page on a phone to
go, for the shop to load on by itself in place of page links, for the size
guide to carry his own figures, and for Click's mark beside its payment
method. Sizes sold out of order, and a list that could show one design twice,
were found on the way and are held here too.

Each class is one of those, written as what a visitor sees or as the rule in
the stylesheet that makes it so.
"""
import importlib
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from payment.models import PAYMENT_LOGOS, PaymentOption
from product import size_charts
from product.models import (SIZE_LADDER, Colour, Product, Size, SizeChart, SizeChartRow,
                            Variant, size_rank)

from .test_phase4 import make_product
from .test_phase16 import CheckoutCase

ROOT = Path(settings.BASE_DIR)
CSS = ROOT / 'static' / 'css'
JS = ROOT / 'static' / 'js'
TEMPLATES = ROOT / 'templates'


def stylesheet(name):
    """A stylesheet as written, with its comments taken out."""
    text = (CSS / name).read_text(encoding='utf-8')
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def tokens():
    """Every colour token of the palette: ``{'--c-bg': '#FFFFFF', ...}``."""
    return dict(re.findall(r'(--c-[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b', stylesheet('tokens.css')))


def luminance(colour):
    """The relative luminance WCAG measures contrast with."""
    def channel(value):
        v = int(value, 16) / 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = (colour[i:i + 2] for i in (1, 3, 5))
    return .2126 * channel(r) + .7152 * channel(g) + .0722 * channel(b)


def contrast(one, two):
    """The contrast ratio of two colours, from 1 to 21."""
    lighter, darker = sorted((luminance(one), luminance(two)), reverse=True)
    return (lighter + .05) / (darker + .05)


def models_at(app, migration):
    """The models as they stood once ``migration`` had run: what a migration is handed.

    They have no ``save`` of the project's and send no signals, so a test that
    hands them to a migration's function runs what the server will run.
    """
    return MigrationLoader(connection).project_state((app, migration)).apps


def rules_for(css, selector):
    """The declarations of every rule in ``css`` whose selector is ``selector``."""
    found = re.findall(r'(?:^|[}{;])\s*%s\s*\{([^}]*)\}' % re.escape(selector), css)
    return ' '.join(found)


# ------------------------------------------------------------- the palette

class PaletteTests(SimpleTestCase):
    """§17 #352: a white page, and everything on it still readable."""

    GROUNDS = ('--c-bg', '--c-surface', '--c-surface-2', '--c-surface-3')

    def setUp(self):
        self.c = tokens()

    def test_the_page_is_white_and_the_ink_is_not_black(self):
        self.assertEqual(self.c['--c-bg'].upper(), '#FFFFFF')
        self.assertNotEqual(self.c['--c-fg'], '#000000')
        self.assertGreater(contrast(self.c['--c-fg'], self.c['--c-bg']), 15)

    def test_text_colours_read_on_every_ground(self):
        for ink in ('--c-fg', '--c-fg-muted', '--c-fg-hint', '--c-brand-ink'):
            for ground in self.GROUNDS:
                if (ink, ground) == ('--c-brand-ink', '--c-surface-3'):
                    # A pressed control is never the ground of brass text.
                    continue
                with self.subTest(ink=ink, ground=ground):
                    self.assertGreaterEqual(contrast(self.c[ink], self.c[ground]), 4.5)

    def test_a_state_reads_on_the_page_and_on_its_own_tint(self):
        for state in ('success', 'warning', 'danger', 'info'):
            ink = self.c['--c-%s' % state]
            for ground in ('--c-bg', '--c-surface', '--c-%s-bg' % state):
                with self.subTest(state=state, ground=ground):
                    self.assertGreaterEqual(contrast(ink, self.c[ground]), 4.5)

    def test_the_two_brasses_do_the_two_jobs(self):
        """§17 #353: one to fill and to draw with, a darker one to be read."""
        page = self.c['--c-bg']
        # A fill, an icon, a line, a focus ring: 3:1 against the page.
        self.assertGreaterEqual(contrast(self.c['--c-brand'], page), 3.0)
        # ...and too pale to be text, which is why there is a second one.
        self.assertLess(contrast(self.c['--c-brand'], page), 4.5)
        self.assertGreaterEqual(contrast(self.c['--c-brand-ink'], page), 4.5)
        self.assertGreaterEqual(contrast(self.c['--c-brand-ink'], self.c['--c-brand-bg']), 4.5)
        # What is written on a filled button, at rest and under a pointer.
        for fill in ('--c-brand', '--c-brand-hover'):
            with self.subTest(fill=fill):
                self.assertGreaterEqual(contrast(self.c['--c-brand-fg'], self.c[fill]), 4.5)

    def test_brass_that_is_read_takes_the_darker_brass(self):
        wanted = {
            'base.css': ('.link',),
            'pages.css': ('.pdp__price', '.reviews__avg', '.cartpage__total dd'),
            'components.css': ('.badge--brand', '.sizeguide__table tr.is-current td'),
            'panel.css': ('.stat__n--brand',),
        }
        for sheet, selectors in wanted.items():
            css = stylesheet(sheet)
            for selector in selectors:
                block = [body for sel, body in re.findall(r'([^{}]+)\{([^}]*)\}', css)
                         if selector in [s.strip() for s in sel.split(',')]]
                with self.subTest(sheet=sheet, selector=selector):
                    self.assertTrue(block, 'no rule for %s' % selector)
                    colours = re.findall(r'(?<![-\w])color:\s*([^;]+)', ' '.join(block))
                    self.assertIn('var(--c-brand-ink)', [c.strip() for c in colours])

    def test_a_control_has_a_boundary_on_every_ground(self):
        for ground in self.GROUNDS:
            with self.subTest(ground=ground):
                self.assertGreaterEqual(
                    contrast(self.c['--c-line-control'], self.c[ground]), 3.0)

    def test_the_focus_ring_is_seen_on_every_ground(self):
        """A ring is drawn on panels too, where the paler brass falls short."""
        for sheet in ('base.css', 'components.css', 'pages.css', 'panel.css'):
            css = stylesheet(sheet)
            for colour in re.findall(r'outline:\s*2px solid (var\([^)]+\))', css):
                with self.subTest(sheet=sheet):
                    self.assertEqual(colour, 'var(--c-brand-ink)')
        self.assertIn('outline: 2px solid var(--c-brand-ink)',
                      rules_for(stylesheet('base.css'), ':focus-visible'))
        for ground in self.GROUNDS:
            with self.subTest(ground=ground):
                self.assertGreaterEqual(
                    contrast(self.c['--c-brand-ink'], self.c[ground]), 3.0)
        # The paler brass would not do: it falls short on the first panel.
        self.assertLess(contrast(self.c['--c-brand'], self.c['--c-surface']), 3.0)

    def test_a_boundary_does_not_fade_under_a_pointer(self):
        """The quietest ink is paler than a control's line on a white ground."""
        for sheet in ('components.css', 'pages.css', 'panel.css'):
            for selector, body in re.findall(r'([^{}]+)\{([^}]*)\}', stylesheet(sheet)):
                if ':hover' in selector:
                    with self.subTest(sheet=sheet, selector=selector.strip()):
                        self.assertNotIn('border-color: var(--c-fg-subtle)', body)

    def test_a_step_still_ahead_is_quiet_and_still_read(self):
        steps = rules_for(stylesheet('pages.css'), '.steps__step')
        self.assertIn('color: var(--c-fg-hint)', steps)

    def test_the_manifest_and_the_browser_bar_are_white(self):
        manifest = (TEMPLATES / 'site.webmanifest').read_text(encoding='utf-8')
        self.assertIn('"background_color": "#FFFFFF"', manifest)
        self.assertIn('"theme_color": "#FFFFFF"', manifest)
        for shell in ('base.html', 'boshqaruv/base.html'):
            with self.subTest(shell=shell):
                self.assertIn('<meta name="theme-color" content="#FFFFFF">',
                              (TEMPLATES / shell).read_text(encoding='utf-8'))

    def test_the_style_guide_shows_the_palette_that_ships(self):
        from core.views import STYLE_SWATCHES
        for name, value in STYLE_SWATCHES:
            with self.subTest(token=name):
                self.assertEqual(self.c[name].upper(), value.upper())

    def test_the_pictures_drawn_for_the_site_are_on_the_white_ground(self):
        for name in ('og-image.png', 'size_guide.png'):
            with self.subTest(picture=name), Image.open(ROOT / 'static' / 'img' / name) as im:
                corner = im.convert('RGB').getpixel((2, 2))
                self.assertEqual(corner, (255, 255, 255))


# ---------------------------------------------------------------- the heart

class HeartTests(SimpleTestCase):
    """§17 #355: only the heart takes the brass; its button never fills."""

    def setUp(self):
        self.css = stylesheet('components.css')

    def test_the_floating_heart_has_no_hover_of_its_own(self):
        self.assertNotIn('.like--float:hover', self.css)

    def test_no_rule_gives_a_heart_button_a_brass_ground(self):
        for selector, body in re.findall(r'([^{}]+)\{([^}]*)\}', self.css):
            if '.like' in selector:
                with self.subTest(selector=selector.strip()):
                    self.assertNotRegex(body, r'background:\s*var\(--c-brand\)')

    def test_the_hover_is_only_for_a_pointer_that_can_hover(self):
        """A phone keeps `:hover` on the last thing tapped."""
        outside = re.sub(r'@media\s*\(hover:\s*hover\)\s*\{(?:[^{}]*\{[^}]*\})*\s*\}', '', self.css)
        self.assertNotIn('.like:hover', outside)
        self.assertRegex(self.css, r'@media\s*\(hover:\s*hover\)\s*\{\s*\.like:hover \.i\s*\{')

    def test_the_colour_goes_on_the_icon_and_the_count_stays_in_ink(self):
        pressed = rules_for(self.css, '.like[aria-pressed="true"] .i')
        self.assertIn('color: var(--c-brand)', pressed)
        self.assertNotIn('color', rules_for(self.css, '.like[aria-pressed="true"]'))
        self.assertNotIn('color', rules_for(self.css, '.like__count'))


# -------------------------------------------------------------- the buy bar

class BuyBarTests(TestCase):
    """The bar fixed to the foot of the product page on a phone is gone."""

    def test_the_product_page_has_one_buy_button_and_no_bar(self):
        product, _ = make_product('Barsiz')
        html = self.client.get(reverse('item', kwargs={'slug': product.slug})).content.decode()
        self.assertNotIn('buybar', html)
        self.assertNotIn('data-buy-jump', html)
        self.assertNotIn('pdp__pad', html)
        self.assertEqual(html.count('data-buy'), 1)
        self.assertEqual(html.count('data-price-display'), 1)

    def test_nothing_is_left_of_it_in_the_styles_or_the_script(self):
        for sheet in ('components.css', 'pages.css'):
            with self.subTest(sheet=sheet):
                css = stylesheet(sheet)
                self.assertNotIn('buybar', css)
                self.assertNotIn('pdp__pad', css)
        script = (JS / 'variant.js').read_text(encoding='utf-8')
        self.assertNotIn('data-buy-jump', script)
        self.assertNotIn('data-variant-label', script)


# ---------------------------------------------------------- the endless list

class EndlessListTests(TestCase):
    """§17 #356: the shop adds the next page under the last; the links stay."""

    PER_PAGE = 20

    @classmethod
    def setUpTestData(cls):
        cls.products = [make_product('Dizayn %02d' % n)[0] for n in range(cls.PER_PAGE + 5)]
        # One moment and one price for all of them: every order the shop
        # offers is then a tie from the first row to the last.
        Product.objects.update(created_at=timezone.now())

    def page(self, **query):
        return self.client.get(reverse('shop'), query)

    def test_the_first_page_hands_the_list_to_the_script(self):
        html = self.page().content.decode()
        self.assertIn('data-more-grid', html)
        self.assertRegex(html, r'<div class="more" data-more data-first\b')
        self.assertIn('js/shop.js', html)
        # The way on is still a link, for a browser that runs no script.
        self.assertRegex(html, r'href="\?page=2"\s+rel="next"')
        # What the script may say is in the page, in the page's language.
        self.assertIn('data-loaded="Yana dizaynlar koʻrsatildi."', html)
        self.assertIn('data-more-retry', html)

    def test_a_later_page_keeps_its_links(self):
        html = self.page(page=2).content.decode()
        self.assertIn('data-more', html)
        self.assertNotRegex(html, r'data-more data-first')
        self.assertRegex(html, r'href="\?page=1"\s+rel="prev"')

    def test_filters_travel_with_the_next_page(self):
        html = self.page(sort='popular').content.decode()
        self.assertRegex(html, r'href="\?sort=popular&(amp;)?page=2"\s+rel="next"')

    def test_a_list_of_one_page_has_nothing_to_load(self):
        Product.objects.filter(pk__in=[p.pk for p in self.products[self.PER_PAGE - 2:]]).delete()
        html = self.page().content.decode()
        self.assertIn('data-more-grid', html)
        self.assertNotIn('data-more ', html)
        self.assertNotIn('rel="next"', html)

    def test_no_design_is_on_two_pages_or_on_none(self):
        """Rows that tie come back in any order unless the order says more."""
        everything = {p.pk for p in self.products}
        for sort in ('new', 'popular', 'rating', 'price_asc', 'price_desc'):
            with self.subTest(sort=sort):
                first = [p.pk for p in self.page(sort=sort).context['products']]
                second = [p.pk for p in self.page(sort=sort, page=2).context['products']]
                self.assertEqual(len(first), self.PER_PAGE)
                self.assertEqual(set(first) | set(second), everything)
                self.assertFalse(set(first) & set(second))
                # And the same answer when asked again.
                self.assertEqual(first, [p.pk for p in self.page(sort=sort).context['products']])

    def test_every_order_ends_in_the_rows_own_id(self):
        for sort in ('new', 'popular', 'rating', 'price_asc', 'price_desc'):
            with self.subTest(sort=sort):
                rows = self.page(sort=sort).context['paginator'].object_list
                self.assertEqual(rows.query.order_by[-1], '-pk')

    def test_the_script_says_nothing_of_its_own(self):
        """A string a page can show is copy, and copy is translated (§17 #80)."""
        script = (JS / 'shop.js').read_text(encoding='utf-8')
        code = re.sub(r'/\*.*?\*/', '', script, flags=re.S)
        for word in ('dizayn', 'Yana', 'yukla', 'Loading', 'Загруз'):
            with self.subTest(word=word):
                self.assertNotIn(word, code)

    def test_the_list_is_announced_in_each_language(self):
        for lang, said in (('ru', 'Показаны ещё дизайны.'), ('en', 'More designs are shown.')):
            with self.subTest(lang=lang):
                html = self.client.get('/%s/shop/' % lang).content.decode()
                self.assertIn('data-loaded="%s"' % said, html)


# ------------------------------------------------------------ sizes in order

class SizeOrderTests(TestCase):
    """§17 #358: sizes are sold smallest first, whenever they were added."""

    def test_a_label_on_the_ladder_has_its_place(self):
        self.assertLess(size_rank('XS'), size_rank('S'))
        self.assertLess(size_rank('S'), size_rank('M'))
        self.assertLess(size_rank('XL'), size_rank('XXL'))
        self.assertEqual(size_rank(' xs '), size_rank('XS'))
        # A size named the owner's own way goes after all of them.
        self.assertGreater(size_rank('Bolalar 6-7'), size_rank('5XL'))

    def test_a_size_added_last_is_listed_where_it_belongs(self):
        SizeChartRow.objects.all().delete()
        Size.objects.all().delete()
        for label in ('S', 'M', 'L', 'XL', 'XS', 'Bir oʻlcham', 'XXL'):
            Size.objects.create(size=label)
        self.assertEqual([s.size for s in Size.objects.all()],
                         ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'Bir oʻlcham'])

    def test_a_place_set_by_hand_is_kept(self):
        size = Size.objects.create(size='M', order=5)
        size.save()
        size.refresh_from_db()
        self.assertEqual(size.order, 5)
        # Through a rename as well: it was never the label's place.
        size.size = 'L'
        size.save(update_fields=['size'])
        size.refresh_from_db()
        self.assertEqual(size.order, 5)

    def test_a_label_put_right_moves_the_size_to_its_place(self):
        """Typed as "SX", then corrected in the panel, which saves one field."""
        size = Size.objects.create(size='SX')
        self.assertEqual(size.order, size_rank('SX'))
        size.size = 'XS'
        size.save(update_fields=['size'])
        size.refresh_from_db()
        self.assertEqual(size.order, size_rank('XS'))

    def test_the_panel_rename_does_the_same(self):
        from panel import reference
        SizeChartRow.objects.all().delete()
        Size.objects.all().delete()
        for label in ('S', 'M', 'ХS'):          # the last begins with a Cyrillic letter
            Size.objects.create(size=label)
        wrong = Size.objects.get(size='ХS')
        reference.set_field('size', wrong.pk, 'size', 'XS')
        self.assertEqual([s.size for s in Size.objects.all()], ['XS', 'S', 'M'])

    def test_the_migration_places_the_sizes_that_exist(self):
        """0027, run on rows as 0026 leaves them: every size at nought."""
        migration = importlib.import_module('product.migrations.0027_place_sizes')
        then = models_at('product', '0026_size_order')
        SizeThen = then.get_model('product', 'Size')
        SizeChartRow.objects.all().delete()
        Variant.objects.all().delete()
        SizeThen.objects.all().delete()
        for label in ('S', 'M', 'L', 'XL', 'XS', 'Bir oʻlcham'):
            SizeThen.objects.create(size=label)
        self.assertEqual(set(SizeThen.objects.values_list('order', flat=True)), {0})
        migration.place(then, None)
        self.assertEqual([s.size for s in Size.objects.all()],
                         ['XS', 'S', 'M', 'L', 'XL', 'Bir oʻlcham'])
        self.assertEqual(migration.LADDER, SIZE_LADDER)

    def test_the_product_page_offers_them_in_that_order(self):
        product = Product.objects.create(name='Tartibli')
        colour = Colour.objects.create(colour='Qora')
        for label in ('L', 'XS', 'M'):
            size = Size.objects.filter(size=label).first() or Size.objects.create(size=label)
            Variant.objects.create(product=product, size=size, colour=colour,
                                   price=Decimal('149000'), available=True, stock=3)
        response = self.client.get(reverse('item', kwargs={'slug': product.slug}))
        self.assertEqual([s.size for s in response.context['sizes']], ['XS', 'M', 'L'])
        html = response.content.decode()
        buttons = re.findall(r'class="sizes__btn"[^>]*>\s*([^<\s]+)\s*<', html)
        self.assertEqual(buttons, ['XS', 'M', 'L'])
        # The size chosen for a visitor who chooses none is the first of them.
        self.assertEqual(response.context['selected_variant'].size.size, 'XS')

    def test_the_shops_size_filter_is_in_that_order_too(self):
        product = Product.objects.create(name='Filtrli')
        colour = Colour.objects.create(colour='Oq')
        for label in ('XL', 'XS'):
            size = Size.objects.filter(size=label).first() or Size.objects.create(size=label)
            Variant.objects.create(product=product, size=size, colour=colour,
                                   price=Decimal('149000'), available=True, stock=3)
        labels = [s.size for s in self.client.get(reverse('shop')).context['sizes']]
        self.assertLess(labels.index('XS'), labels.index('XL'))


# ------------------------------------------------------------ the size chart

class SizeChartTests(TestCase):
    """§17 #357: one chart, with the owner's figures, the chest all the way round."""

    def chart(self):
        return SizeChart.objects.get(name=size_charts.NAME)

    def test_the_two_provisional_charts_are_one_chart_now(self):
        self.assertEqual(SizeChart.objects.count(), 1)
        self.assertFalse(SizeChart.objects.filter(
            name__in=('Oddiy qolip (regular)', 'Oversize qolip')).exists())

    def test_it_carries_the_owners_figures_smallest_size_first(self):
        rows = [(r.size.size, str(r.chest_cm), str(r.length_cm), str(r.shoulder_cm), str(r.sleeve_cm))
                for r in self.chart().rows.select_related('size')]
        self.assertEqual(rows, [(label,) + values for label, values in size_charts.MEASURES.items()])
        self.assertEqual(rows[0][:2], ('XS', '110.0'))
        self.assertEqual(rows[-1], ('XL', '126.0', '76.0', '68.0', '21.0'))

    def test_its_note_is_in_three_languages(self):
        chart = self.chart()
        self.assertIn('1–3 sm', chart.note)
        self.assertIn('1–3 см', chart.note_ru)
        self.assertIn('1–3 cm', chart.note_en)

    def test_the_guide_page_prints_whole_centimetres_as_whole_numbers(self):
        html = self.client.get(reverse('size_guide')).content.decode()
        self.assertIn('Koʻkrak aylanasi, sm', html)
        for figure in ('110', '126', '60', '76'):
            with self.subTest(figure=figure):
                self.assertIn('class="num">%s</td>' % figure, html)
        self.assertNotIn('110,0', html)
        self.assertNotIn('110.0', html)
        # One chart: its panel name is not a heading a shopper reads.
        self.assertNotIn('>%s</h2>' % size_charts.NAME, html)
        self.assertIn('Kiyim oʻlchamlari', html)

    def test_two_charts_are_told_apart_by_their_names(self):
        SizeChart.objects.create(name='Xudi')
        html = self.client.get(reverse('size_guide')).content.decode()
        self.assertIn('>%s</h2>' % size_charts.NAME, html)
        self.assertIn('>Xudi</h2>', html)

    def test_the_columns_are_in_the_owners_order(self):
        html = self.client.get(reverse('size_guide')).content.decode()
        head = html.split('<thead>', 1)[1].split('</thead>', 1)[0]
        order = [head.index(label) for label in
                 ('Koʻkrak aylanasi, sm', 'Yelka, sm', 'Yeng, sm', 'Uzunlik, sm')]
        self.assertEqual(order, sorted(order))
        # XS: chest, shoulder, sleeve, length.
        row = re.search(r'<tr>\s*(?:\{#.*?#\}\s*)*<td[^>]*>XS</td>(.*?)</tr>', html, re.S).group(1)
        self.assertEqual(re.findall(r'>(\d+)</td>', row), ['110', '60', '17', '65'])

    def test_the_rebuild_makes_the_same_rows(self):
        chart = self.chart()
        SizeChartRow.objects.filter(chart=chart).delete()
        size_charts.rebuild_rows({s.size: s for s in Size.objects.all()})
        self.assertEqual(chart.rows.count(), len(size_charts.MEASURES))


class SizeChartMigrationTests(TestCase):
    """What migration 0028 does to a shop that still has the two seeded charts."""

    def setUp(self):
        self.migration = importlib.import_module('product.migrations.0028_owner_size_chart')
        # The shop as it stood before: the two charts, and one of the owner's own.
        SizeChart.objects.all().delete()
        self.regular = SizeChart.objects.create(name='Oddiy qolip (regular)')
        self.oversize = SizeChart.objects.create(name='Oversize qolip')
        self.own = SizeChart.objects.create(name='Xudi')
        small = Size.objects.filter(size='S').first() or Size.objects.create(size='S')
        for chart, chest in ((self.regular, '48.0'), (self.oversize, '54.0'), (self.own, '70.0')):
            SizeChartRow.objects.create(chart=chart, size=small, chest_cm=chest, length_cm='69.0')

    def run_it(self):
        """Run it as `migrate` does: on the models of the migration before it."""
        self.migration.replace(models_at('product', '0027_place_sizes'), None)

    def test_products_on_either_chart_end_on_the_one_that_is_kept(self):
        on_regular, _ = make_product('Oddiy', size_chart=self.regular)
        on_oversize, _ = make_product('Keng', size_chart=self.oversize)
        on_own, _ = make_product('Xudi', size_chart=self.own)
        without, _ = make_product('Jadvalsiz')
        self.run_it()

        kept = SizeChart.objects.get(name=self.migration.NAME)
        self.assertEqual(kept.pk, self.oversize.pk)
        self.assertFalse(SizeChart.objects.filter(pk=self.regular.pk).exists())
        for product, chart in ((on_regular, kept), (on_oversize, kept), (on_own, self.own)):
            product.refresh_from_db()
            self.assertEqual(product.size_chart_id, chart.pk)
        # Which products a chart describes stays the owner's choice.
        without.refresh_from_db()
        self.assertIsNone(without.size_chart_id)

    def test_the_owners_own_chart_is_not_touched(self):
        self.run_it()
        self.own.refresh_from_db()
        self.assertEqual(self.own.name, 'Xudi')
        self.assertEqual([str(r.chest_cm) for r in self.own.rows.all()], ['70.0'])

    def test_the_kept_chart_has_the_new_rows_and_only_those(self):
        self.run_it()
        kept = SizeChart.objects.get(name=self.migration.NAME)
        self.assertEqual([(r.size.size, str(r.chest_cm)) for r in kept.rows.select_related('size')],
                         [(label, values[0]) for label, values in self.migration.MEASURES.items()])

    def test_it_makes_a_chart_where_neither_seeded_one_is_left(self):
        SizeChart.objects.filter(pk__in=(self.regular.pk, self.oversize.pk)).delete()
        self.run_it()
        made = SizeChart.objects.get(name=self.migration.NAME)
        self.assertEqual(made.rows.count(), len(self.migration.MEASURES))

    def test_a_size_it_has_to_make_is_made_in_its_place(self):
        SizeChartRow.objects.all().delete()
        Variant.objects.all().delete()
        Size.objects.all().delete()
        self.run_it()
        self.assertEqual([s.size for s in Size.objects.all()], ['XS', 'S', 'M', 'L', 'XL'])
        self.assertEqual({s.size: s.order for s in Size.objects.all()},
                         {label: size_rank(label) for label in self.migration.MEASURES})

    def test_a_size_typed_in_small_letters_is_the_same_size(self):
        SizeChartRow.objects.all().delete()
        Variant.objects.all().delete()
        Size.objects.all().delete()
        small = Size.objects.create(size='xs')
        self.run_it()
        self.assertEqual(Size.objects.filter(size__iexact='XS').count(), 1)
        kept = SizeChart.objects.get(name=self.migration.NAME)
        self.assertEqual(kept.rows.get(order=0).size_id, small.pk)

    def test_run_again_it_makes_no_second_chart(self):
        on_regular, _ = make_product('Oddiy', size_chart=self.regular)
        self.run_it()
        self.run_it()
        self.assertEqual(SizeChart.objects.filter(name=self.migration.NAME).count(), 1)
        kept = SizeChart.objects.get(name=self.migration.NAME)
        self.assertEqual(kept.rows.count(), len(self.migration.MEASURES))
        on_regular.refresh_from_db()
        self.assertEqual(on_regular.size_chart_id, kept.pk)

    def test_the_figures_are_the_ones_the_site_keeps(self):
        self.assertEqual(self.migration.MEASURES, size_charts.MEASURES)
        self.assertEqual(self.migration.NAME, size_charts.NAME)


class ChoosingTableTests(TestCase):
    """The owner's guide to choosing: a height and a weight for each size."""

    def test_the_guide_page_has_a_row_for_each_size(self):
        html = self.client.get(reverse('size_guide')).content.decode()
        self.assertIn('Oʻlchamni tanlash', html)
        for label, (height, weight) in size_charts.FIT.items():
            with self.subTest(size=label):
                # A range is one value that cannot break at its dash (§17 #204).
                self.assertRegex(html, r'<th scope="row">%s</th>\s*<td class="num">%d\u2060–\u2060%d</td>'
                                       r'\s*<td class="num">%d\u2060–\u2060%d</td>'
                                       % ((label,) + height + weight))
        self.assertIn('Tavsiyalar taxminiy.', html)

    def test_it_is_written_in_each_language(self):
        for lang, heading, column in (('ru', 'Подбор размера', 'Рост, см'),
                                      ('en', 'Choosing a size', 'Height, cm')):
            with self.subTest(lang=lang):
                html = self.client.get('/%s/olcham-jadvali/' % lang).content.decode()
                self.assertIn(heading, html)
                self.assertIn(column, html)

    def test_on_a_product_each_row_knows_its_size(self):
        """So the viewer can mark the row for the size the customer picked."""
        product = Product.objects.create(name='Tanlovli')
        colour = Colour.objects.create(colour='Qora')
        large = Size.objects.filter(size='L').first() or Size.objects.create(size='L')
        Variant.objects.create(product=product, size=large, colour=colour,
                               price=Decimal('149000'), available=True, stock=3)
        html = self.client.get(reverse('item', kwargs={'slug': product.slug})).content.decode()
        block = html.split('data-sizeguide-content', 1)[1]
        self.assertRegex(block, r'<tr data-row-size="%d">\s*<th scope="row">L</th>' % large.pk)
        # A size this product is not made in is still in the table, unmarked.
        self.assertRegex(block, r'<tr>\s*<th scope="row">XS</th>')

    def test_it_stays_a_table_on_a_phone(self):
        partial = (TEMPLATES / 'product' / '_size_fit.html').read_text(encoding='utf-8')
        self.assertIn('table--keep', partial)
        css = stylesheet('components.css')
        self.assertRegex(css, r'\.table--keep\s*\{\s*display:\s*table;')

    def test_rows_without_sizes_carry_no_ids(self):
        self.assertTrue(all(row['size_id'] is None for row in size_charts.fit_rows()))
        self.assertEqual([row['label'] for row in size_charts.fit_rows()], list(size_charts.FIT))


# ------------------------------------------------------------- Click's mark

class ClickLogoTests(CheckoutCase):
    """Click's own mark before the word Click at the checkout."""

    def mark(self, code):
        """The mark's file as text: a drawing, so it is read and not opened."""
        spec = PAYMENT_LOGOS[code]
        path = finders.find(spec['src'])
        self.assertIsNotNone(path, spec['src'])
        return Path(path).read_text(encoding='utf-8'), spec

    def test_every_mark_named_has_its_file(self):
        """A name with no file behind it is an error on the checkout page."""
        for code in PAYMENT_LOGOS:
            with self.subTest(method=code):
                drawing, spec = self.mark(code)
                box = re.search(r'viewBox="([^"]+)"', drawing).group(1).split()
                wide, tall = float(box[2]), float(box[3])
                # The shape it is drawn in is the shape it is shown at.
                self.assertAlmostEqual(wide / tall, spec['width'] / spec['height'], delta=.03)

    def test_it_is_the_mark_alone_as_click_draws_it(self):
        drawing, spec = self.mark('click')
        self.assertTrue(drawing.lstrip().startswith('<svg'))
        self.assertEqual(spec['width'], spec['height'])
        # One shape in Click's blue, with nothing behind it and no word in it:
        # the word is written beside it.
        self.assertEqual(drawing.count('<path'), 1)
        self.assertIn('fill="#0065FF"', drawing)
        self.assertNotIn('<rect', drawing)
        self.assertNotIn('<text', drawing)
        # Nothing a drawing could run or fetch.
        for word in ('<script', 'href', 'onload'):
            with self.subTest(word=word):
                self.assertNotIn(word, drawing)

    def test_it_stands_before_the_name_at_its_own_size(self):
        html = self.client.get(reverse('checkout')).content.decode()
        label = html.split('name="payment_method" value="click"', 1)[1].split('</label>', 1)[0]
        tag = re.search(r'<img class="pay__mark"[^>]*>', label).group(0)
        self.assertIn('img/pay/click', tag)
        self.assertIn('width="24"', tag)
        self.assertIn('height="24"', tag)
        # The name is written beside it, so the picture is not read out twice.
        self.assertIn('alt=""', tag)
        # The radio, then the mark, then the name and the note.
        self.assertLess(label.index('pay__mark'), label.index('<strong>Click</strong>'))
        self.assertLess(label.index('<strong>Click</strong>'), label.index('field__hint'))

    def test_a_method_with_no_mark_is_shown_by_name_alone(self):
        PaymentOption.objects.filter(code='cash').update(is_active=True)
        self.assertIsNone(PaymentOption.objects.get(code='cash').logo)
        html = self.client.get(reverse('checkout')).content.decode()
        marked = [row for row in PaymentOption.objects.filter(is_active=True) if row.logo]
        self.assertEqual(html.count('pay__mark'), len(marked))
        cash = html.split('name="payment_method" value="cash"', 1)[1].split('</label>', 1)[0]
        self.assertNotIn('<img', cash)
