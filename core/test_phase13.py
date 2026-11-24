"""Phase 13: recommendations by tag overlap (plan §9 Phase 13).

"Siz uchun" puts the designs that share tags with what the visitor has liked
first; a guest, or a visitor with no likes, gets the most-liked list the row
was before, so it is never empty. A product's page shows the designs most like
it. Both rows are counted for a signed-in visitor, so one can be held against
the other. The Definition of Done, written as assertions.
"""
import io

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from product import recommend, services
from product.models import Category, Product, RowStat, Tag
from product.views import POPULAR

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase12 import make_order
from .test_phase23 import card_names, for_you_of


class RecommendCase(TestCase):
    """Seven designs under three tags, and one customer.

    Retro: A, B, C. Anime: D, E. Minimal: F. C is also anime. G has no tag in
    common with anything. F is the most liked, so the most-liked order starts
    with it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.retro = Tag.objects.create(name='Retro-13', slug='retro-13')
        cls.anime = Tag.objects.create(name='Anime-13', slug='anime-13')
        cls.minimal = Tag.objects.create(name='Minimal-13', slug='minimal-13')
        cls.lonely = Tag.objects.create(name='Yolgʻiz-13', slug='yolgiz-13')
        cls.shirts = Category.objects.create(name='Futbolkalar-13')
        cls.p = {}
        for name, tags in (('A', [cls.retro]), ('B', [cls.retro]), ('C', [cls.retro, cls.anime]),
                           ('D', [cls.anime]), ('E', [cls.anime]), ('F', [cls.minimal]),
                           ('G', [cls.lonely])):
            product, variant = make_product('Dizayn %s' % name, category=cls.shirts)
            product.tags.set(tags)
            cls.p[name] = product
            setattr(cls, 'variant_%s' % name, variant)
        Product.objects.filter(pk=cls.p['F'].pk).update(likes_count=9)
        cls.user = make_user()

    def setUp(self):
        cache.clear()

    def like(self, *names):
        for name in names:
            services.toggle_like(self.user, self.p[name])

    def home(self):
        return self.client.get(reverse('home')).content.decode()

    def for_you(self):
        return [name.replace('Dizayn ', '') for name in card_names(for_you_of(self.home()))]


class ScoreTests(RecommendCase):
    """What a design scores for one visitor."""

    def test_a_design_scores_the_tags_it_shares_with_the_likes(self):
        self.like('A')
        self.assertEqual(recommend.scores(self.user),
                         {self.p['B'].pk: 1, self.p['C'].pk: 1})

    def test_two_liked_designs_with_a_tag_weigh_twice(self):
        self.like('A', 'D')
        found = recommend.scores(self.user)
        # C is retro like A and anime like D.
        self.assertEqual(found[self.p['C'].pk], 2)
        self.assertEqual(found[self.p['B'].pk], 1)
        self.assertEqual(found[self.p['E'].pk], 1)

    def test_what_was_liked_or_bought_is_left_out(self):
        self.like('A')
        make_order(self.user, self.variant_B, status='paid')
        cache.clear()
        found = recommend.scores(self.user)
        self.assertNotIn(self.p['A'].pk, found)
        self.assertNotIn(self.p['B'].pk, found)
        self.assertIn(self.p['C'].pk, found)

    def test_an_unpaid_order_is_not_a_purchase(self):
        self.like('A')
        make_order(self.user, self.variant_B, status='paying')
        cache.clear()
        self.assertIn(self.p['B'].pk, recommend.scores(self.user))

    def test_a_guest_and_a_visitor_with_no_likes_score_nothing(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(recommend.scores(AnonymousUser()), {})
        self.assertEqual(recommend.scores(self.user), {})

    def test_it_is_one_statement_and_then_the_cache(self):
        self.like('A')
        with CaptureQueriesContext(connection) as first:
            recommend.scores(self.user)
        self.assertEqual(len(first), 1)
        with CaptureQueriesContext(connection) as second:
            recommend.scores(self.user)
        self.assertEqual(len(second), 0)

    def test_a_heart_drops_the_cached_scores(self):
        self.like('A')
        recommend.scores(self.user)
        self.like('F')
        self.assertIsNone(cache.get('recommend:%d' % self.user.pk))


class ForYouTests(RecommendCase):
    """The home page's row, and the shop's pages that carry it on."""

    def test_a_guest_gets_the_most_liked_list(self):
        names = self.for_you()
        self.assertEqual(names[0], 'F')
        self.assertEqual(len(names), 7)

    def test_a_visitor_with_no_likes_gets_the_most_liked_list(self):
        self.client.force_login(self.user)
        self.assertEqual(self.for_you()[0], 'F')

    def test_likes_put_the_designs_like_them_first(self):
        self.like('A', 'D')
        self.client.force_login(self.user)
        names = self.for_you()
        # C shares a tag with each like; B and E with one; then the rest,
        # the most liked first.
        self.assertEqual(names[0], 'C')
        self.assertEqual(set(names[1:3]), {'B', 'E'})
        self.assertEqual(names[3], 'F')
        # Never empty and never short: everything on sale is still there.
        self.assertEqual(len(names), 7)

    def test_the_next_pages_are_asked_for_in_the_same_order(self):
        for n in range(20):
            make_product('Yana %d' % n)
        self.like('A')
        self.client.force_login(self.user)
        section = for_you_of(self.home())
        self.assertRegex(section, r'href="%s\?sort=foryou&(amp;)?page=2"' % reverse('shop'))
        first = card_names(section)
        second = card_names(self.client.get(reverse('shop'), {'sort': 'foryou', 'page': 2})
                            .content.decode())
        self.assertEqual(len(first), 20)
        self.assertFalse(set(first) & set(second))

    def test_a_guest_who_asks_for_it_gets_the_most_liked_order(self):
        response = self.client.get(reverse('shop'), {'sort': 'foryou'})
        self.assertEqual(response.context['sort'], 'popular')
        self.assertEqual(card_names(response.content.decode())[0], 'Dizayn F')
        self.assertNotIn('value="foryou"', response.content.decode())

    def test_the_shop_names_the_order_while_it_is_shown(self):
        self.like('A')
        self.client.force_login(self.user)
        html = self.client.get(reverse('shop'), {'sort': 'foryou'}).content.decode()
        self.assertIn('<option value="foryou" selected>Siz uchun</option>', html)
        self.assertNotIn('value="foryou"', self.client.get(reverse('shop')).content.decode())


class SimilarTests(RecommendCase):
    """The strip on a product's page."""

    def strip(self, name):
        response = self.client.get(reverse('item', args=[self.p[name].slug]))
        return [p.name.replace('Dizayn ', '') for p in response.context['related']]

    def test_the_designs_sharing_its_tags_come_first(self):
        names = self.strip('C')
        # A, B, D and E each share one of C's two tags; F and G share none.
        self.assertEqual(set(names), {'A', 'B', 'D', 'E'})

    def test_the_most_alike_is_first(self):
        twin, _variant = make_product('Dizayn T', category=self.shirts)
        twin.tags.set([self.retro, self.anime])
        self.assertEqual(self.strip('C')[0], 'T')

    def test_it_is_filled_where_few_share_a_tag(self):
        names = self.strip('G')
        self.assertEqual(len(names), 4)
        # Nothing shares its tag, so the most liked of its category leads.
        self.assertEqual(names[0], 'F')
        self.assertNotIn('G', names)

    def test_a_design_off_sale_is_not_offered(self):
        Product.objects.filter(pk=self.p['A'].pk).update(is_active=False)
        self.assertNotIn('A', self.strip('B'))

    def test_the_ids_cost_at_most_three_statements(self):
        with CaptureQueriesContext(connection) as queries:
            recommend.similar(self.p['G'], POPULAR)
        self.assertLessEqual(len(queries), 3)


class MeasureTests(RecommendCase):
    """Shown and opened, a signed-in visitor's only."""

    def count(self, row):
        stat = RowStat.objects.filter(row=row).first()
        return (stat.shown, stat.clicked) if stat else (0, 0)

    def test_a_guest_is_not_counted_and_their_links_are_plain(self):
        html = self.home()
        self.client.get(reverse('item', args=[self.p['A'].slug]), {'r': 'fy'})
        self.assertNotIn('?r=', html)
        self.assertFalse(RowStat.objects.exists())

    def test_the_baseline_is_counted_for_a_visitor_with_no_likes(self):
        self.client.force_login(self.user)
        section = for_you_of(self.home())
        self.assertIn('href="%s?r=pl"' % reverse('item', args=[self.p['F'].slug]), section)
        self.assertEqual(self.count('pl'), (1, 0))
        self.client.get(reverse('item', args=[self.p['F'].slug]), {'r': 'pl'})
        self.assertEqual(self.count('pl'), (1, 1))

    def test_the_row_by_likes_is_counted_on_its_own(self):
        self.like('A')
        self.client.force_login(self.user)
        section = for_you_of(self.home())
        self.assertIn('?r=fy"', section)
        self.home()
        self.client.get(reverse('item', args=[self.p['B'].slug]), {'r': 'fy'})
        self.assertEqual(self.count('fy'), (2, 1))
        self.assertEqual(self.count('pl'), (0, 0))

    def test_only_the_last_row_carries_the_mark_on_the_home_page(self):
        self.client.force_login(self.user)
        html = self.home()
        newest = html.split('aria-labelledby="newest"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('?r=', newest)

    def test_the_strip_is_counted(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('item', args=[self.p['A'].slug])).content.decode()
        self.assertIn('?r=sm"', html)
        self.assertEqual(self.count('sm'), (1, 0))

    def test_an_unknown_mark_counts_nothing(self):
        self.client.force_login(self.user)
        self.client.get(reverse('item', args=[self.p['A'].slug]), {'r': 'zz'})
        self.assertFalse(RowStat.objects.filter(row='zz').exists())

    def test_the_report_holds_one_against_the_other(self):
        RowStat.objects.create(day='2026-11-25', row='fy', shown=40, clicked=10)
        RowStat.objects.create(day='2026-11-25', row='pl', shown=50, clicked=5)
        out = io.StringIO()
        call_command('recommend_report', days=3650, stdout=out)
        report = out.getvalue()
        self.assertIn('25.0%', report)
        self.assertIn('10.0%', report)
        self.assertIn('no data', report)
