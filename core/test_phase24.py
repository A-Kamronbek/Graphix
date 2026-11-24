"""Phase 24: the home page redrawn (plan §9 Phase 24).

The page opens with its heading at the size of a poster and three designs
dealt beside it, keeps the owner's slides, shows six new designs (from 860 px
the first of them large), states the delivery prices on a dark band from the
rows that enforce them, draws the categories as tiles and sets the own-design
band on the ink. These tests hold what a later change could lose without
anybody seeing it: the one heading, the order of the blocks, the figures'
source and the rules the layout stands on.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from core.views import HERO_SHOTS, NEWEST
from payment.models import DeliveryOption
from product.models import Category, Product
from product.templatetags.image_tags import SIZES

from .test_phase4 import make_product

CSS = Path(settings.BASE_DIR) / 'static' / 'css'


def sheet(name):
    """A stylesheet with its comments taken out, so prose cannot match."""
    return re.sub(r'/\*.*?\*/', '', (CSS / name).read_text(encoding='utf-8'), flags=re.S)


class HomeCase(TestCase):
    """Two categories with designs, a third with none, and eleven designs in all."""

    @classmethod
    def setUpTestData(cls):
        cls.shirts = Category.objects.create(name='Futbolkalar', name_ru='Футболки', name_en='T-shirts')
        cls.hoodies = Category.objects.create(name='Xudi', name_ru='Худи', name_en='Hoodies')
        cls.empty = Category.objects.create(name='Shimlar')
        for n in range(1, 10):
            make_product('Futbolka %d' % n, category=cls.shirts)
        make_product('Xudi 1', category=cls.hoodies)
        cls.newest, _variant = make_product('Xudi 2', category=cls.hoodies)

    def setUp(self):
        cache.delete('delivery_tiers')

    def page(self, language='uz'):
        with translation.override(language):
            return self.client.get(reverse('home')).content.decode()


class HeroTests(HomeCase):
    """The heading, the shop's line and the two ways in."""

    def test_the_page_has_one_heading_and_it_is_seen(self):
        html = self.page()
        self.assertEqual(html.count('<h1'), 1)
        hero = html.split('class="hero"', 1)[1].split('</section>', 1)[0]
        self.assertRegex(hero, r'<h1 class="hero__title">Grafik futbolkalar<svg')
        self.assertNotIn('sr-only', hero)

    def test_it_leads_to_the_shop_and_to_ones_own_design(self):
        hero = self.page().split('class="hero"', 1)[1].split('</section>', 1)[0]
        self.assertIn('href="%s"' % reverse('shop'), hero)
        self.assertIn('href="%s"' % reverse('custom_design'), hero)

    def test_its_words_are_in_each_language(self):
        for language, heading in (('ru', 'Футболки с принтами'), ('en', 'Graphic T-shirts')):
            with self.subTest(language=language):
                self.assertIn('<h1 class="hero__title">%s<svg' % heading, self.page(language))

    def test_the_blocks_come_in_their_order(self):
        html = self.page()
        marks = ['class="hero"', 'id="newest"', 'class="homefacts"', 'class="tiles"',
                 'class="own"', 'id="for-you"']
        places = [html.index(mark) for mark in marks]
        self.assertEqual(places, sorted(places))


class DeckTests(HomeCase):
    """The most-liked designs dealt beside the heading."""

    def test_three_designs_are_dealt_and_each_leads_to_its_page(self):
        Product.objects.filter(pk=self.newest.pk).update(likes_count=7)
        deck = self.page().split('class="hero__deck"', 1)[1].split('</ul>', 1)[0]
        self.assertEqual(deck.count('class="hero__shot"'), HERO_SHOTS)
        # The most liked is dealt first.
        self.assertLess(deck.index('href="%s"' % reverse('item', args=[self.newest.slug])),
                        deck.index('</li>'))
        # Not drawn on a phone, so not fetched there either.
        self.assertEqual(deck.count('loading="lazy"'), HERO_SHOTS)
        self.assertIn('.hero__actions, .hero__deck { display: none; }', sheet('pages.css'))

    def test_with_nothing_on_sale_there_is_no_deck(self):
        Product.objects.update(is_active=False)
        self.assertNotIn('hero__deck', self.page())


class NewestTests(HomeCase):
    """Six designs; from 860 px the newest is large and the sixth is not drawn."""

    def block(self, language='uz'):
        return self.page(language).split('aria-labelledby="newest"', 1)[1].split('</section>', 1)[0]

    def test_there_are_six_and_the_newest_is_first(self):
        block = self.block()
        names = re.findall(r'<span class="card__name">([^<]*)</span>', block)
        self.assertEqual(NEWEST, 6)
        self.assertEqual(len(names), NEWEST)
        self.assertEqual(names[0], 'Xudi 2')
        self.assertIn('class="grid-products grid-products--lead"', block)

    def test_the_first_card_asks_for_its_photograph_first(self):
        block = self.block()
        # One photograph on the page asks for priority, and it is the first.
        self.assertEqual(block.count('fetchpriority="high"'), 1)
        self.assertLess(block.index('fetchpriority="high"'), block.index('</article>'))
        # The first four are in or near the first screen; the rest wait.
        self.assertEqual(block.count('loading="lazy"'), NEWEST - 4)
        # A card like the others on a phone, four cells of the grid on a laptop.
        self.assertIn('(min-width: 860px) 46vw', SIZES['card-lead'])
        self.assertTrue(SIZES['card-lead'].endswith(', 46vw'))

    def test_the_large_card_waits_for_a_laptop(self):
        css = sheet('pages.css')
        first = '.grid-products--lead > .card:first-child { grid-column: span 2; grid-row: span 2;'
        before, after = css.split(first, 1)
        # The rule is the first inside its 860 px block, and no rule before
        # it makes the first card larger than the rest.
        self.assertRegex(before, r'@media \(min-width: 860px\) \{\s*$')
        self.assertNotIn('.grid-products--lead', before)
        self.assertIn('.grid-products--lead > .card:nth-child(6) { display: none; }',
                      after.split('.homefacts {', 1)[0])

    def test_nothing_on_the_page_moves_by_itself_for_long(self):
        """No band that runs and no sticker: the owner's slides are the one thing that advances."""
        html = self.page()
        self.assertNotIn('ticker', html)
        self.assertNotIn('sticker', html)
        self.assertNotIn('infinite', sheet('pages.css').split('.hero {', 1)[1].split('.own__grid', 1)[0])


class FactsTests(HomeCase):
    """The delivery prices on the band are the rows' own (§17 #111)."""

    def test_a_changed_price_is_the_price_the_band_says(self):
        option = DeliveryOption.objects.filter(is_active=True).first()
        if option is None:
            option = DeliveryOption.objects.create(code='uzpost_office', name='Pochta boʻlimiga',
                                                   price=15000, is_active=True)
        DeliveryOption.objects.filter(pk=option.pk).update(price=23000)
        cache.delete('delivery_tiers')
        band = self.page().split('class="homefacts"', 1)[1].split('</section>', 1)[0]
        self.assertIn('23 000', band.replace('\xa0', ' '))

    def test_it_leads_to_delivery_and_returns(self):
        band = self.page().split('class="homefacts"', 1)[1].split('</section>', 1)[0]
        for name in ('delivery', 'returns'):
            with self.subTest(name=name):
                self.assertIn('href="%s"' % reverse(name), band)


class TileTests(HomeCase):
    """A tile for each category with a design on sale."""

    def tiles(self, language='uz'):
        return self.page(language).split('class="tiles"', 1)[1].split('</ul>', 1)[0]

    def test_a_category_with_nothing_on_sale_has_no_tile(self):
        tiles = self.tiles()
        self.assertEqual(re.findall(r'class="tile__name">([^<]+)<', tiles), ['Futbolkalar', 'Xudi'])
        self.assertNotIn('category=%d"' % self.empty.pk, tiles)

    def test_a_tile_counts_what_is_on_sale_and_leads_to_it(self):
        Product.objects.filter(name='Futbolka 1').update(is_active=False)
        tiles = self.tiles()
        self.assertIn('href="%s?category=%d"' % (reverse('shop'), self.shirts.pk), tiles)
        self.assertEqual(re.findall(r'class="tile__count num">([^<]+)<', tiles),
                         ['8 ta mahsulot', '2 ta mahsulot'])

    def test_a_tile_is_named_in_the_pages_language(self):
        self.assertIn('class="tile__name">Худи<', self.tiles('ru'))
        self.assertIn('class="tile__name">Hoodies<', self.tiles('en'))

    def test_with_no_category_there_is_no_block(self):
        Product.objects.update(category=None)
        self.assertNotIn('class="tiles"', self.page())


class ColourTests(SimpleTestCase):
    """The dark ground: tokens, and a focus ring that shows on it."""

    def test_the_ink_and_what_stands_on_it_are_tokens(self):
        tokens = sheet('tokens.css')
        for name in ('--c-ink:', '--c-on-ink:', '--c-on-ink-muted:', '--c-ink-line:', '--c-ink-mark:'):
            with self.subTest(name=name):
                self.assertIn(name, tokens)

    def test_the_focus_ring_is_light_on_the_ink(self):
        self.assertIn('.homefacts :focus-visible, .own :focus-visible { outline-color: var(--c-on-ink); }',
                      sheet('pages.css'))

    def test_the_page_has_no_second_accent(self):
        """Brass is the one accent; a red was tried and taken out at the developer's word."""
        self.assertNotIn('--c-signal', sheet('tokens.css'))
        self.assertNotIn('--c-signal', sheet('pages.css'))

    def test_the_home_pages_rules_use_no_raw_colour(self):
        css = sheet('pages.css')
        home = css.split('.hero {', 1)[1].split('.own__grid { grid-template-columns', 1)[0]
        self.assertEqual(re.findall(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', home), [])
