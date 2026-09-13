"""Phase 6h: the language switcher, and the data a dropped pin needs.

The switcher test is the important one. Switching language worked once and then
silently stopped — every later click reloaded the same page in the same
language — and nothing in the suite noticed, because nothing had ever driven
the control rather than rendering it. These tests operate the real forms: they
read what the page actually puts in them and post exactly that.
"""
import json
import re

from django.test import TestCase
from django.urls import reverse

from .test_phase4 import make_product


# The pages a visitor is most likely to be on when they reach for the switcher.
PAGES = ['/', '/shop/', '/about/', '/yetkazib-berish/']
PREFIX = {'uz': '', 'ru': '/ru', 'en': '/en'}


class LanguageSwitchTests(TestCase):
    """Every language reachable from every language, on every page.

    Uzbek is unprefixed, which is what broke this: `/i18n/setlang/` carries no
    language prefix either, and Django forces the default language on any
    unprefixed path when `prefix_default_language=False`. `set_language` was
    therefore always running in Uzbek and could not resolve a `/ru/` path in
    order to translate it, so it redirected to whatever it was given — which
    was the page the visitor was already on (§17 #115).
    """

    @classmethod
    def setUpTestData(cls):
        make_product('Til sinovi', stock=3)

    def forms(self, path):
        """The switcher's real forms on a rendered page: {code: next}."""
        html = self.client.get(path, follow=True).content.decode()
        out = {}
        for block in re.findall(r'<form[^>]*setlang[^>]*>(.*?)</form>', html, re.S):
            nxt = re.search(r'name="next" value="([^"]*)"', block)
            code = re.search(r'name="language" value="([^"]*)"', block)
            if nxt and code:
                out[code.group(1)] = nxt.group(1)
        return out

    def test_every_page_offers_all_three_languages(self):
        for path in PAGES:
            with self.subTest(path=path):
                self.assertEqual(set(self.forms(path)), {'uz', 'ru', 'en'})

    def test_each_button_carries_this_page_in_that_language(self):
        """The form's `next` is already translated — that is the whole fix."""
        for path in PAGES:
            for code, nxt in self.forms(path).items():
                with self.subTest(path=path, code=code):
                    self.assertEqual(nxt, PREFIX[code] + path)

    def test_switching_lands_on_the_same_page_in_the_new_language(self):
        for path in PAGES:
            for start in ('uz', 'ru', 'en'):
                start_path = PREFIX[start] + path
                for target in ('uz', 'ru', 'en'):
                    with self.subTest(path=path, start=start, target=target):
                        forms = self.forms(start_path)
                        response = self.client.post(
                            reverse('set_language'),
                            {'next': forms[target], 'language': target})
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(response.headers['Location'],
                                         PREFIX[target] + path)

    def test_the_page_it_lands_on_really_is_in_that_language(self):
        """A redirect to the right URL is not the same as the right page."""
        for target in ('uz', 'ru', 'en'):
            with self.subTest(target=target):
                forms = self.forms('/ru/shop/')
                response = self.client.post(reverse('set_language'),
                                            {'next': forms[target], 'language': target},
                                            follow=True)
                self.assertContains(response, 'lang="%s"' % target)

    def test_a_query_string_survives_the_switch(self):
        forms = self.forms('/shop/?sort=popular')
        self.assertEqual(forms['ru'], '/ru/shop/?sort=popular')
        response = self.client.post(reverse('set_language'),
                                    {'next': forms['ru'], 'language': 'ru'})
        self.assertEqual(response.headers['Location'], '/ru/shop/?sort=popular')

    def test_the_switcher_is_in_the_mobile_drawer_too(self):
        """It has its own copy of the control, and it had the same defect."""
        html = self.client.get('/').content.decode()
        drawer = html.split('drawer__lang', 1)
        self.assertEqual(len(drawer), 2, 'the drawer switcher is missing')
        self.assertIn('name="next" value="/ru/"', drawer[1])


class PinDataTests(TestCase):
    """A dropped pin can only fill a field it can match a row to.

    Google names places in its own words — Chilonzor is "Chilanzar District" in
    English — so every row ships all three of its spellings for the browser to
    compare against (§17 #116).
    """

    def setUp(self):
        from core.test_phase6 import make_user
        from cart.models import Cart, CartItem
        from payment.models import DeliveryOption          # noqa: F401  (seeded)
        from core.test_phase6 import make_regions
        self.geo = make_regions()
        self.user = make_user('xaritachi', '+998901234522')
        product, variant = make_product('Xarita', stock=4)
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1,
                                price_stat=variant.price)

    def test_every_region_option_carries_all_three_spellings(self):
        html = self.client.get(reverse('checkout')).content.decode()
        matches = re.findall(r'data-match="([^"]*)"', html)
        self.assertTrue(matches, 'no region carries a data-match')
        for value in matches:
            self.assertEqual(len(value.split('|')), 3, value)

    def test_every_district_ships_its_names_for_matching(self):
        response = self.client.get(reverse('checkout'))
        data = json.loads(response.context['districts_json'])
        seen = 0
        for region in data.values():
            for kind in ('district', 'city', 'other'):
                for row in region[kind]:
                    self.assertIn('match', row)
                    self.assertTrue(row['match'], row)
                    seen += 1
        self.assertGreater(seen, 0)

    def test_the_maps_loader_asks_for_the_pages_language(self):
        """Names in the page's language match our rows more often, and the
        address line comes back readable rather than transliterated."""
        with self.settings(GOOGLE_MAPS_API_KEY='test-key'):
            html = self.client.get(reverse('checkout')).content.decode()
        self.assertIn('language=uz', html)
        self.assertIn('region=UZ', html)

    def test_no_map_and_no_loader_without_a_key(self):
        with self.settings(GOOGLE_MAPS_API_KEY=''):
            html = self.client.get(reverse('checkout')).content.decode()
        self.assertNotIn('maps.googleapis.com', html)
        self.assertNotIn('data-map-canvas', html)
