"""A phone can sign out: from its menu on every page, and at the foot of the account pages.

Kamronbek's report and call (§17 #305). Since Phase 5 the only sign-out was
the account sidebar's button, and the stylesheet hid it below 860 px, where
the sidebar becomes a row of tabs - so a phone had no way to sign out at all.
The laptop's button is where it was; a phone gets one in the menu, under
Kabinet and Buyurtmalarim, and one at the foot of Kabinet, Buyurtmalarim and
Sozlamalar.

All three are the same form (`partials/_logout.html`): a POST with its CSRF
token, because the logout view takes nothing else.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .test_phase6 import make_user

ACCOUNT_PAGES = ('account', 'account_orders', 'account_settings')


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
        self.assertIn('class="drawer__action"', forms[0])
        self.assertIn('Chiqish', forms[0])

    def test_it_sits_under_the_account_links(self):
        self.client.force_login(make_user('tartibli', '+998901280102'))
        menu = drawer(self.client.get(reverse('shop')).content.decode())
        orders = menu.index(reverse('account_orders'))
        signout = menu.index('action="%s"' % reverse('logout'))
        about = menu.index(reverse('about'))
        self.assertLess(orders, signout)
        self.assertLess(signout, about)

    def test_signed_out_the_menu_offers_no_sign_out(self):
        menu = drawer(self.client.get(reverse('home')).content.decode())
        self.assertEqual(signout_forms(menu), [])
        self.assertIn(reverse('login'), menu)


class AccountPageTests(TestCase):
    """Kabinet, Buyurtmalarim and Sozlamalar carry the sidebar's and the foot's."""

    def setUp(self):
        self.client.force_login(make_user('kabinetchi', '+998901280103'))

    def test_each_account_page_has_both(self):
        for name in ACCOUNT_PAGES:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                outside_menu = html.replace(drawer(html), '')
                classes = [form.split('>', 1)[0] for form in signout_forms(outside_menu)]
                self.assertEqual(len(classes), 2)
                self.assertIn('class="account__logout"', classes[0])
                self.assertIn('class="account__logout account__logout--foot"', classes[1])

    def test_the_foot_comes_after_the_page(self):
        html = self.client.get(reverse('account_settings')).content.decode()
        self.assertLess(html.index(reverse('account_forgot_password')),
                        html.index('account__logout--foot'))

    def test_the_foot_signs_out(self):
        """The button posts to the view that has always done it."""
        self.client.post(reverse('logout'))
        response = self.client.get(reverse('account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class StylesheetTests(TestCase):
    """One copy per screen: the sidebar's from 860 px, the foot's below it."""

    CSS = (Path(settings.BASE_DIR) / 'static' / 'css' / 'pages.css').read_text(encoding='utf-8')

    def test_below_860_the_foot_shows_and_the_sidebar_does_not(self):
        account = self.CSS.split('/* --------------------------------------------------------------- account */', 1)[1]
        section = account.split('@media (min-width: 860px)', 1)[0]
        self.assertIn('.account__logout { display: none; }', section)
        self.assertIn('.account__logout--foot { display: block; }', section)
        self.assertLess(section.index('.account__logout { display: none; }'),
                        section.index('.account__logout--foot { display: block; }'))

    def test_from_860_the_sidebar_shows_and_the_foot_does_not(self):
        account = self.CSS.split('/* --------------------------------------------------------------- account */', 1)[1]
        wide = account.split('@media (min-width: 860px) {', 1)[1].split('\n}', 1)[0]
        self.assertIn('.account__logout { display: block; margin-top: var(--s-4); }', wide)
        self.assertIn('.account__logout--foot { display: none; }', wide)
