"""A phone can sign out: from the foot of its menu on every page, and from the foot of Kabinet.

Kamronbek's report and calls (§17 #305, #306). Since Phase 5 the only
sign-out was the account sidebar's button, and the stylesheet hid it below
860 px, where the sidebar becomes a row of tabs - so a phone had no way to
sign out at all. The laptop's button is where it was. A phone has a bordered
button at the bottom of its menu, under the languages, and one at the foot of
Kabinet; Buyurtmalarim and Sozlamalar do not carry one (#306).

All three are the same form (`partials/_logout.html`): a POST with its CSRF
token, because the logout view takes nothing else.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .test_phase6 import make_user

FOOT = 'class="account__logout account__logout--foot"'


def signout_forms(html):
    """Every sign-out form on a page, as its opening tag through its button."""
    action = 'action="%s"' % reverse('logout')
    return [chunk.split('</form>', 1)[0] for chunk in html.split('<form')[1:]
            if chunk.split('>', 1)[0].count(action)]


def drawer(html):
    return html.split('id="gx-drawer"', 1)[1].split('</nav>', 1)[0]


class PhoneMenuTests(TestCase):
    """The menu a phone opens from the header."""

    def test_signed_in_the_menu_can_sign_out(self):
        self.client.force_login(make_user('menyuchi', '+998901280101'))
        forms = signout_forms(drawer(self.client.get(reverse('home')).content.decode()))
        self.assertEqual(len(forms), 1)
        self.assertIn('method="post"', forms[0])
        self.assertIn('csrfmiddlewaretoken', forms[0])
        self.assertIn('class="drawer__logout"', forms[0])
        self.assertIn('class="btn btn--secondary btn--block"', forms[0])
        self.assertIn('Chiqish', forms[0])

    def test_it_is_last_under_the_languages_not_in_the_list(self):
        self.client.force_login(make_user('tartibli', '+998901280102'))
        menu = drawer(self.client.get(reverse('shop')).content.decode())
        signout = menu.index('action="%s"' % reverse('logout'))
        self.assertLess(menu.index('</ul>'), signout)
        self.assertLess(menu.index('drawer__lang'), signout)
        self.assertLess(menu.index(reverse('set_language')), signout)

    def test_signed_out_the_menu_offers_no_sign_out(self):
        menu = drawer(self.client.get(reverse('home')).content.decode())
        self.assertEqual(signout_forms(menu), [])
        self.assertIn(reverse('login'), menu)


class AccountPageTests(TestCase):
    """Kabinet has the sidebar's and the foot's; the other two the sidebar's alone."""

    def setUp(self):
        self.client.force_login(make_user('kabinetchi', '+998901280103'))

    def forms(self, name):
        html = self.client.get(reverse(name)).content.decode()
        return [form.split('>', 1)[0] for form in signout_forms(html.replace(drawer(html), ''))]

    def test_kabinet_has_both(self):
        forms = self.forms('account')
        self.assertEqual(len(forms), 2)
        self.assertIn('class="account__logout"', forms[0])
        self.assertIn(FOOT, forms[1])

    def test_orders_and_settings_have_the_sidebar_only(self):
        for name in ('account_orders', 'account_settings'):
            with self.subTest(page=name):
                forms = self.forms(name)
                self.assertEqual(len(forms), 1)
                self.assertIn('class="account__logout"', forms[0])

    def test_the_foot_comes_after_the_page(self):
        html = self.client.get(reverse('account')).content.decode()
        self.assertLess(html.index('account__nav'), html.index('account__logout--foot'))
        self.assertLess(html.index('Soʻnggi buyurtmalar'), html.index('account__logout--foot'))

    def test_signing_out_works(self):
        """The buttons post to the view that has always done it."""
        self.client.post(reverse('logout'))
        response = self.client.get(reverse('account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class StylesheetTests(TestCase):
    """One copy per screen: the sidebar's from 860 px, the foot's below it."""

    CSS = (Path(settings.BASE_DIR) / 'static' / 'css' / 'pages.css').read_text(encoding='utf-8')
    COMPONENTS = (Path(settings.BASE_DIR) / 'static' / 'css' / 'components.css').read_text(encoding='utf-8')
    MARK = '/* --------------------------------------------------------------- account */'

    def test_below_860_the_foot_shows_and_the_sidebar_does_not(self):
        section = self.CSS.split(self.MARK, 1)[1].split('@media (min-width: 860px)', 1)[0]
        self.assertIn('.account__logout { display: none; }', section)
        self.assertIn('.account__logout--foot { display: block; }', section)
        self.assertLess(section.index('.account__logout { display: none; }'),
                        section.index('.account__logout--foot { display: block; }'))

    def test_from_860_the_sidebar_shows_and_the_foot_does_not(self):
        wide = self.CSS.split(self.MARK, 1)[1].split('@media (min-width: 860px) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('.account__logout { display: block; margin-top: var(--s-4); }', wide)
        self.assertIn('.account__logout--foot { display: none; }', wide)

    def test_the_menu_button_is_spaced_from_the_languages(self):
        self.assertIn('.drawer__logout { margin-top: var(--s-6); }', self.CSS)

    def test_the_list_row_style_is_gone(self):
        self.assertNotIn('drawer__action', self.COMPONENTS)
