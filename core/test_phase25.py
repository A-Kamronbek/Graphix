"""Phase 25: the other pages drawn as the home page is (plan §9 Phase 25).

The foot of every page stands on the ink with the shop's name across it, the
about page has the home page's heading over three numbered rows, and the page
for a wrong address shows its number at a poster's size. These tests hold what
a later change could lose without anybody seeing it.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

CSS = Path(settings.BASE_DIR) / 'static' / 'css'


def sheet(name):
    """A stylesheet with its comments taken out, so prose cannot match."""
    return re.sub(r'/\*.*?\*/', '', (CSS / name).read_text(encoding='utf-8'), flags=re.S)


def rule(css, selector):
    """The declarations of the first rule that opens with ``selector``."""
    return css.split(selector + ' {', 1)[1].split('}', 1)[0]


class FootTests(TestCase):
    """The foot of every page, on the ink."""

    def foot(self, name='about'):
        html = self.client.get(reverse(name)).content.decode()
        return html.split('<footer class="foot">', 1)[1].split('</footer>', 1)[0]

    def test_it_stands_on_the_ink_in_tokens(self):
        css = sheet('components.css')
        self.assertIn('background: var(--c-ink)', rule(css, '.foot'))
        self.assertIn('color: var(--c-on-ink-muted)', rule(css, '.foot'))
        self.assertIn('color: var(--c-on-ink)', rule(css, '.foot h2'))
        block = css.split('.foot {', 1)[1].split('.foot__word {', 1)[1].split('}', 1)[0]
        self.assertEqual(re.findall(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', block), [])

    def test_its_focus_ring_and_its_link_show_on_the_ink(self):
        css = sheet('components.css')
        self.assertIn('.foot :focus-visible { outline-color: var(--c-on-ink); }', css)
        # Brass that is read on the page is too dark on the ink; the fill's tone is not.
        self.assertIn('.foot .link { color: var(--c-brand);', css)

    def test_the_name_across_it_is_drawn_and_not_read(self):
        foot = self.foot()
        self.assertIn('<p class="foot__word" aria-hidden="true">GRAPHIX</p>', foot)
        self.assertIn('--foot-word:', sheet('tokens.css'))

    def test_it_still_says_what_it_said(self):
        for name in ('home', 'shop', 'about'):
            with self.subTest(name=name):
                foot = self.foot(name)
                for target in ('shop', 'contact', 'about', 'returns', 'terms', 'privacy', 'delivery'):
                    self.assertIn('href="%s"' % reverse(target), foot)


class AboutTests(TestCase):
    """The about page: one heading, three rows, two ways on."""

    def page(self, language='uz'):
        with translation.override(language):
            return self.client.get(reverse('about')).content.decode()

    def test_it_has_one_heading_with_the_mark(self):
        html = self.page()
        self.assertEqual(html.count('<h1'), 1)
        self.assertRegex(html, r'<h1 class="hero__title">Biz haqimizda<svg class="hero__mark"')

    def test_it_has_three_numbered_rows(self):
        html = self.page()
        self.assertEqual(html.count('class="about__row"'), 3)
        self.assertEqual(re.findall(r'class="about__no num" aria-hidden="true">(\d\d)<', html),
                         ['01', '02', '03'])
        self.assertEqual(html.count('<h2 class="about__h">'), 3)

    def test_it_reads_in_each_language(self):
        for language, heading in (('ru', 'О нас'), ('en', 'About us')):
            with self.subTest(language=language):
                self.assertIn('<h1 class="hero__title">%s<svg' % heading, self.page(language))

    def test_it_leads_to_the_shop_and_to_contact(self):
        html = self.page().split('class="wrap about"', 1)[1].split('</article>', 1)[0]
        self.assertIn('href="%s"' % reverse('shop'), html)
        self.assertIn('href="%s"' % reverse('contact'), html)


class WrongAddressTests(TestCase):
    """The 404 page: its number large, its two ways out in the middle."""

    @override_settings(DEBUG=False)
    def test_the_number_is_drawn_and_the_heading_is_the_words(self):
        response = self.client.get('/uz/bunday-sahifa-yoq/')
        self.assertEqual(response.status_code, 404)
        html = response.content.decode()
        self.assertIn('<p class="empty__code num" aria-hidden="true">404</p>', html)
        self.assertEqual(html.count('<h1'), 1)
        self.assertIn('href="%s"' % reverse('shop'), html)


class EmptyStateTests(SimpleTestCase):
    """What an empty state's rules must keep."""

    def test_its_buttons_stand_in_the_middle(self):
        self.assertIn('.empty .row { justify-content: center; }', sheet('components.css'))

    def test_the_number_is_a_token_and_pale(self):
        css = sheet('components.css')
        code = rule(css, '.empty .empty__code')
        self.assertIn('var(--fs-poster)', code)
        self.assertIn('color: var(--c-surface-3)', code)
        self.assertIn('--fs-poster:', sheet('tokens.css'))
