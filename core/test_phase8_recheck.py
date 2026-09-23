"""Phase 8, rechecked: the answers to §19 Q27-Q31, the Telegram bot service,
and what a line-by-line pass over the phase found.

Each class names the decision it holds in place (§17 #205-#214). Like the rest
of Phase 8's tests, most of these read a rendered page rather than a function:
a legal page goes wrong silently, and only the page shows it.
"""
import hashlib
import hmac
import importlib
import json
import os
import re
import time
from pathlib import Path
from unittest import mock

import requests
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import Resolver404, clear_url_caches, resolve, reverse
from django.utils import translation

from cart.models import Cart, CartItem
from core import legal, telegram, views
from core.runner import OFFLINE, go_offline
from payment.models import DeliveryOption, Order

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order

LANGS = ('uz', 'ru', 'en')
ROOT = Path(settings.BASE_DIR)
TEMPLATES = ROOT / 'templates'
PROBE = '/.well-known/appspecific/com.chrome.devtools.json'

#: The legal form in each language, as the documents print it mid-sentence.
FORM = {'uz': 'yakka tartibdagi tadbirkor',
        'ru': 'индивидуальный предприниматель',
        'en': 'sole proprietor'}

#: A bot service, as a test sets one up. The token and chat id stay blank, so
#: a relayed event that fell through to the Bot API would fail loudly.
RELAY = {'TELEGRAM_BOT_WEBHOOK_URL': 'https://bot.example.test/graphix/events',
         'WEBSITE_WEBHOOK_SECRET': 's3cret-for-tests-only',
         'TELEGRAM_BOT_TOKEN': '', 'TELEGRAM_CHAT_ID': ''}


def text(client, path, **extra):
    """The page at ``path``, as text."""
    return client.get(path, **extra).content.decode()


def section(html, anchor):
    """One ``<section id=anchor>`` of a rendered document."""
    start = html.index(f'id="{anchor}"')
    return html[start:html.index('</section>', start)]


def answered(status=200):
    """A stand-in for ``requests.post`` that answers ``status``."""
    return mock.patch('core.telegram.requests.post',
                      return_value=mock.Mock(status_code=status, text='answer'))


def sent(post):
    """The JSON body and the headers of the one request ``post`` made."""
    _, kwargs = post.call_args
    return json.loads(kwargs['data'].decode('utf-8')), kwargs['headers']


class DarkReaderLockTests(TestCase):
    """§17 #205: the site is dark by design and tells the browser so."""

    METAS = ('<meta name="color-scheme" content="dark">', '<meta name="darkreader-lock">')

    def assert_locked(self, html, where):
        for meta in self.METAS:
            with self.subTest(where=where, meta=meta):
                self.assertIn(meta, html)

    def test_every_template_with_a_head_carries_both(self):
        heads = [p for p in TEMPLATES.rglob('*.html')
                 if '<head>' in p.read_text(encoding='utf-8')]
        self.assertGreaterEqual(len(heads), 3)
        for path in heads:
            self.assert_locked(path.read_text(encoding='utf-8'), path.name)

    def test_the_storefront_the_panel_the_style_guide_and_an_error_page(self):
        self.assert_locked(text(self.client, '/uz/'), 'home')
        self.assert_locked(text(self.client, '/uz/no-such-page/'), '404')
        self.client.force_login(make_staff('qorongi', '+998901400001'))
        self.assert_locked(text(self.client, '/uz/boshqaruv/'), 'panel')
        self.assert_locked(text(self.client, '/uz/boshqaruv/style/'), 'style guide')


class BrowserProbeTests(SimpleTestCase):
    """§17 #213: the two paths browsers ask for on their own."""

    def test_favicon_ico_redirects_to_the_icon(self):
        response = self.client.get('/favicon.ico')
        self.assertRedirects(response, static('img/favicon.ico'), status_code=301,
                             fetch_redirect_response=False)
        self.assertTrue(finders.find('img/favicon.ico'))

    def test_the_favicon_stays_outside_the_language_prefix(self):
        for code in LANGS:
            with self.subTest(code=code), translation.override(code):
                self.assertEqual(reverse('favicon'), '/favicon.ico')

    def test_the_devtools_probe_is_answered_empty(self):
        response = views.devtools_probe(RequestFactory().get(PROBE))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')

    def test_the_probe_is_routed_in_development_only(self):
        import config.urls as root

        def reload_routes():
            importlib.reload(root)
            clear_url_caches()

        with self.assertRaises(Resolver404):         # the suite runs with DEBUG off
            resolve(PROBE)
        self.addCleanup(reload_routes)               # back to DEBUG-off routes
        with self.settings(DEBUG=True):
            reload_routes()
            self.assertIs(resolve(PROBE).func, views.devtools_probe)


class RelayTests(SimpleTestCase):
    """§17 #206: with a bot service set, every notification goes there, signed."""

    def test_an_event_is_posted_once_signed_and_never_redirected(self):
        with self.settings(**RELAY), answered() as post:
            self.assertTrue(telegram.deliver('order.paid', '<b>Toʻlandi</b>',
                                             {'order': {'id': 1}}))
        self.assertEqual(post.call_count, 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], RELAY['TELEGRAM_BOT_WEBHOOK_URL'])
        self.assertIs(kwargs['allow_redirects'], False)
        self.assertEqual(kwargs['timeout'], telegram.TIMEOUT)

        body, headers = sent(post)
        self.assertEqual(body['event'], 'order.paid')
        self.assertEqual(body['text'], '<b>Toʻlandi</b>')
        self.assertEqual(body['parse_mode'], 'HTML')
        self.assertEqual(body['data'], {'order': {'id': 1}})
        self.assertRegex(body['sent_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d')

        self.assertEqual(headers['X-Webhook-Event'], 'order.paid')
        self.assertEqual(headers['X-Webhook-Secret'], RELAY['WEBSITE_WEBHOOK_SECRET'])
        self.assertTrue(headers['Content-Type'].startswith('application/json'))
        stamp = headers['X-Webhook-Timestamp']
        self.assertLess(abs(time.time() - int(stamp)), 60)
        expected = hmac.new(RELAY['WEBSITE_WEBHOOK_SECRET'].encode(),
                            stamp.encode() + b'.' + kwargs['data'],
                            hashlib.sha256).hexdigest()
        self.assertEqual(headers['X-Webhook-Signature'], f'sha256={expected}')

    def test_the_bot_api_is_left_alone_while_relaying(self):
        with self.settings(**RELAY), answered(), \
                mock.patch('core.telegram.send') as direct:
            telegram.deliver('order.paid', 'x', {})
        direct.assert_not_called()

    def test_without_a_bot_service_the_bot_api_route_is_unchanged(self):
        with mock.patch('core.telegram.send', return_value=True) as direct, \
                answered() as post:
            self.assertTrue(telegram.deliver('order.paid', 'salom', {}))
        direct.assert_called_once_with('salom', preview=False)
        post.assert_not_called()

    def test_nothing_is_sent_without_the_secret(self):
        with self.settings(**{**RELAY, 'WEBSITE_WEBHOOK_SECRET': ''}), answered() as post, \
                self.assertLogs('core.telegram', 'ERROR'):
            self.assertFalse(telegram.deliver('order.paid', 'x', {}))
        post.assert_not_called()

    def test_the_secret_only_travels_over_https_or_inside_this_machine(self):
        for url, allowed in (('http://bot.example.test/hook', False),
                             ('ftp://bot.example.test/hook', False),
                             ('https:///hook', False),
                             ('http://127.0.0.1:8080/hook', True),
                             ('http://localhost:8080/hook', True),
                             ('https://bot.example.test/hook', True)):
            with self.subTest(url=url), answered() as post, \
                    self.settings(**{**RELAY, 'TELEGRAM_BOT_WEBHOOK_URL': url}), \
                    self.assertLogs('core.telegram', 'DEBUG') as logs:
                telegram.logger.debug('start')     # assertLogs needs one line
                self.assertEqual(telegram.deliver('order.paid', 'x', {}), allowed)
            self.assertEqual(post.called, allowed)
            if not allowed:
                self.assertIn('https://', '\n'.join(logs.output))

    def test_anything_but_a_2xx_is_a_failure_and_the_secret_stays_out_of_the_log(self):
        for status in (204, 301, 302, 401, 404, 500):
            with self.subTest(status=status), self.settings(**RELAY), answered(status), \
                    self.assertLogs('core.telegram', 'DEBUG') as logs:
                telegram.logger.debug('start')
                self.assertEqual(telegram.deliver('order.paid', 'x', {}), status == 204)
            self.assertNotIn(RELAY['WEBSITE_WEBHOOK_SECRET'], '\n'.join(logs.output))

    def test_a_failure_of_any_kind_is_swallowed(self):
        for error in (requests.ConnectionError('down'), requests.Timeout('slow'),
                      ValueError('odd')):
            with self.subTest(error=error), self.settings(**RELAY), \
                    mock.patch('core.telegram.requests.post', side_effect=error), \
                    self.assertLogs('core.telegram', 'ERROR'):
                self.assertFalse(telegram.deliver('order.paid', 'x', {}))


class RelayedEventTests(TestCase):
    """The three events, relayed, with the facts behind each message."""

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('uzatuvchi', '+998901400002')
        self.product, self.variant = make_product('Relay', stock=5)
        self.client.force_login(self.user)

    def relayed(self, action):
        """Run ``action`` with the bot service set; the one request it made."""
        with self.settings(**RELAY), answered() as post:
            with self.captureOnCommitCallbacks(execute=True):
                action()
        self.assertEqual(post.call_count, 1)
        return sent(post)

    def _checkout(self):
        """Place an order through the real form. Returns it."""
        cart = Cart.objects.create(user=self.user, status=True)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=2,
                                price_stat=self.variant.price)
        self.client.post(reverse('checkout'), {
            'name': 'Qabul Qiluvchi', 'phone': '+998 90 140 00 02',
            'delivery_option': 'uzpost_door',
            'region': self.geo['tashkent'].pk, 'district': self.geo['chilonzor'].pk,
            'address': 'Amir Temur koʻchasi 1', 'address_source': 'manual',
            'payment_method': 'click', 'notes': '<i>eshik yonida</i>',
        })
        return Order.objects.get(cart=cart)

    def test_a_checkout_relays_nothing_until_it_is_paid(self):
        """§17 #237: an order that is still `paying` is not a parcel."""
        with self.settings(**RELAY), answered() as post:
            with self.captureOnCommitCallbacks(execute=True):
                self._checkout()
        self.assertEqual(post.call_count, 0)

    def test_a_paid_order_relays_the_order_and_its_facts(self):
        order = self._checkout()
        body, headers = self.relayed(lambda: telegram.notify_paid_order(order))
        self.assertEqual(body['event'], 'order.paid')
        self.assertEqual(headers['X-Webhook-Event'], 'order.paid')
        self.assertIn('Yangi buyurtma', body['text'])
        self.assertIn('toʻlandi', body['text'])
        self.assertIn('&lt;i&gt;eshik yonida&lt;/i&gt;', body['text'])

        data = body['data']['order']
        self.assertEqual(data['number'], order.order_no)
        self.assertEqual(data['total'], int(order.total_price))
        self.assertEqual(data['status'], order.status)
        self.assertEqual(data['recipient'], {'name': 'Qabul Qiluvchi', 'phone': order.phone})
        self.assertEqual(data['delivery']['code'], 'uzpost_door')
        self.assertIs(data['delivery']['to_branch'], False)
        self.assertEqual(data['address'], order.location_snapshot)
        self.assertIsNone(data['location'])
        self.assertEqual(data['notes'], '<i>eshik yonida</i>')
        self.assertEqual(data['items'], [{'product': 'Relay', 'size': self.variant.size.size,
                                          'quantity': 2, 'price': int(self.variant.price)}])
        # The link leads to the panel's own order screen, by its number.
        self.assertTrue(data['admin_url'].endswith(
            '/uz/boshqaruv/buyurtmalar/%s/' % order.order_no), data['admin_url'])

    def test_the_paid_event_is_the_one_a_real_payment_sends(self):
        """The service, not the helper: the callback is what fires this."""
        from payment import services as payment_services
        order = self._checkout()
        body, _ = self.relayed(
            lambda: payment_services.apply_successful_payment(order))
        self.assertEqual(body['event'], 'order.paid')
        self.assertEqual(body['data']['order']['status'], 'paid')

    def test_a_contact_message_relays(self):
        body, _ = self.relayed(lambda: self.client.post(
            reverse('contact'), {'subject': 'Savol', 'message': 'Salom'}))
        self.assertEqual(body['event'], 'message.created')
        message = body['data']['message']
        self.assertEqual((message['subject'], message['text']), ('Savol', 'Salom'))
        self.assertEqual(message['username'], 'uzatuvchi')

    def test_a_review_relays(self):
        from product.models import Review
        order = make_order(self.user, self.variant, status='done')
        body, _ = self.relayed(lambda: Review.objects.create(
            user=self.user, product=self.product, order=order, rating=4, text='Yaxshi'))
        self.assertEqual(body['event'], 'review.created')
        self.assertEqual(body['data']['review']['rating'], 4)
        self.assertIs(body['data']['review']['has_photos'], False)


class OfflineRunTests(SimpleTestCase):
    """§17 #207: whatever a developer's .env says, the suite notifies nobody."""

    def test_the_run_starts_with_every_notification_setting_blank(self):
        for name in OFFLINE:
            with self.subTest(name=name):
                self.assertEqual(getattr(settings, name), '')
                self.assertEqual(os.environ.get(name), '')

    def test_going_offline_blanks_the_process_and_what_it_starts(self):
        filled = {name: 'from-a-real-env' for name in OFFLINE}
        with mock.patch.dict(os.environ, filled), self.settings(**filled):
            go_offline()
            for name in OFFLINE:
                self.assertEqual(getattr(settings, name), '')
                self.assertEqual(os.environ[name], '')

    def test_both_bot_service_values_are_read_from_the_environment(self):
        source = (ROOT / 'config' / 'settings.py').read_text(encoding='utf-8')
        for name in ('TELEGRAM_BOT_WEBHOOK_URL', 'WEBSITE_WEBHOOK_SECRET'):
            with self.subTest(name=name):
                self.assertIn(f'{name} = os.environ.get("{name}", "")', source)

    def test_the_example_env_documents_them_and_holds_no_secret(self):
        example = (ROOT / '.env.example').read_text(encoding='utf-8')
        for name in ('TELEGRAM_BOT_WEBHOOK_URL', 'WEBSITE_WEBHOOK_SECRET'):
            with self.subTest(name=name):
                self.assertRegex(example, rf'(?m)^{name}=\s*$')

    def test_the_contract_names_every_header_the_site_sends(self):
        contract = (ROOT / 'docs' / 'integrations' / 'telegram-bot.md').read_text(
            encoding='utf-8')
        with self.settings(**RELAY), answered() as post:
            telegram.deliver('order.paid', 'x', {})
        _, headers = sent(post)
        for header in headers:
            with self.subTest(header=header):
                self.assertIn(f'`{header}`', contract)
        for event in ('order.paid', 'message.created', 'review.created'):
            with self.subTest(event=event):
                self.assertIn(f'`{event}`', contract)


class SellerFormTests(TestCase):
    """§17 #208, #209: a sole proprietor, at a Qoʻqon address."""

    def test_the_address_carries_qoqons_index(self):
        address = legal.SELLER['address']
        self.assertTrue(address.startswith('150700, '), address)
        self.assertIn('Qoʻqon shahri', address)
        self.assertNotIn('700000', address.replace('150700', ''))

    def test_the_form_in_three_languages(self):
        for lang in LANGS:
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(str(legal.facts().seller.legal_form), FORM[lang])

    def test_the_terms_name_the_seller_by_form_and_name(self):
        name = legal.SELLER['registered_name']
        for lang in LANGS:
            html = text(self.client, f'/{lang}/terms/')
            with self.subTest(lang=lang):
                self.assertIn(f'{FORM[lang]} {name}', section(html, 'general'))
                self.assertIn(f'<dd>{FORM[lang][0].upper()}{FORM[lang][1:]}</dd>',
                              section(html, 'seller'))

    def test_the_privacy_policy_names_the_controller_by_form(self):
        seller = legal.SELLER
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(f"{FORM[lang]} {seller['registered_name']} ({seller['brand']})",
                              section(text(self.client, f'/{lang}/privacy/'), 'controller'))

    def test_the_contact_page_states_the_form(self):
        for lang, label in (('uz', 'Yakka tartibdagi tadbirkor'),
                            ('ru', 'Индивидуальный предприниматель'),
                            ('en', 'Sole proprietor')):
            with self.subTest(lang=lang):
                self.assertIn(f'<span class="small muted">{label}</span>',
                              text(self.client, f'/{lang}/contact/'))


class HoldPeriodTests(TestCase):
    """§17 #210: an ordinary parcel waits a month, and the pages say one month."""

    EXPECTED = {
        'uz': ('joʻnatmani 1 oy saqlaydi', 'Joʻnatma boʻlimda 1 oy saqlanadi.'),
        'ru': ('хранит посылку 1 месяц.', 'Отделение хранит посылку 1 месяц.'),
        'en': ('holds the parcel for 1 month.', 'The branch holds the parcel for 1 month.'),
    }

    def setUp(self):
        geo = make_regions()
        self.user = make_user('kutuvchi', '+998901400003')
        _, variant = make_product('Kutish', stock=3)
        self.order = make_order(self.user, variant, status='paid')
        Order.objects.filter(pk=self.order.pk).update(
            delivery_option=DeliveryOption.objects.get(code='uzpost_office'),
            region=geo['tashkent'], district=geo['chilonzor'], postal_index='100011')
        self.client.force_login(self.user)

    def order_page(self, lang):
        return text(self.client, f'/{lang}/order/{self.order.pk}/')

    def test_the_rule_is_one_month_and_nothing_asks_for_a_range(self):
        self.assertEqual(legal.BRANCH_HOLD_MONTHS, 1)
        facts = legal.facts()
        self.assertEqual(facts.hold_months, 1)
        self.assertFalse(hasattr(facts, 'hold_min') or hasattr(facts, 'hold_max'))
        stale = [p.name for p in TEMPLATES.rglob('*.html')
                 if re.search(r'hold_(min|max)', p.read_text(encoding='utf-8'))]
        self.assertEqual(stale, [])

    def test_every_page_that_states_it_says_one_month(self):
        for lang, (document, order) in self.EXPECTED.items():
            with self.subTest(lang=lang):
                self.assertIn(document, section(text(self.client, f'/{lang}/terms/'),
                                                'uncollected'))
                self.assertIn(document, section(text(self.client, f'/{lang}/yetkazib-berish/'),
                                                'uncollected'))
                self.assertIn(order, self.order_page(lang))

    def test_the_word_follows_the_number(self):
        for months, ru, en in ((2, '2 месяца', '2 months'), (5, '5 месяцев', '5 months')):
            with self.subTest(months=months), \
                    mock.patch.object(legal, 'BRANCH_HOLD_MONTHS', months):
                self.assertIn(f'Отделение хранит посылку {ru}.', self.order_page('ru'))
                self.assertIn(f'The branch holds the parcel for {en}.', self.order_page('en'))
                self.assertIn(f'хранит посылку {ru}.',
                              text(self.client, '/ru/yetkazib-berish/'))
                self.assertIn(f'holds the parcel for {en}.',
                              text(self.client, '/en/yetkazib-berish/'))


class ServerAbroadTests(TestCase):
    """§17 #211: the policy says the site's own data is kept in Warsaw."""

    WHERE = {'uz': ('Polshada, Varshava shahrida', 'GDPR'),
             'ru': ('в Польше, в Варшаве', 'GDPR'),
             'en': ('Warsaw, Poland', 'GDPR')}

    def test_the_transfer_section_names_the_country_and_its_law(self):
        for lang, words in self.WHERE.items():
            abroad = section(text(self.client, f'/{lang}/privacy/'), 'abroad')
            for word in words:
                with self.subTest(lang=lang, word=word):
                    self.assertIn(word, abroad)

    def test_the_hosting_line_says_where_and_points_there(self):
        for lang in LANGS:
            recipients = section(text(self.client, f'/{lang}/privacy/'), 'recipients')
            with self.subTest(lang=lang):
                self.assertIn('href="#abroad"', recipients)
                self.assertRegex(recipients, 'Varshava|Варшава|Warsaw')


class BackLinkTests(TestCase):
    """§17 #212: "back" never returns to the page the reader is on."""

    def back(self, path, referer):
        return self.client.get(path, HTTP_REFERER=referer).context['back_url']

    def test_the_same_document_in_another_language_is_not_back(self):
        for came_from in ('http://testserver/uz/terms/',
                          'http://testserver/en/terms/?x=1#seller'):
            with self.subTest(came_from=came_from):
                self.assertEqual(self.back('/ru/terms/', came_from), '/ru/')

    def test_another_page_in_another_language_is(self):
        came_from = 'http://testserver/uz/signup/'
        self.assertEqual(self.back('/ru/terms/', came_from), came_from)

    def test_another_document_is(self):
        came_from = 'http://testserver/ru/privacy/'
        self.assertEqual(self.back('/ru/terms/', came_from), came_from)

    def test_a_path_that_is_not_a_page_is_not(self):
        self.assertEqual(self.back('/uz/privacy/', 'http://testserver/uz/no-such-page/'), '/uz/')


class EmailBreakTests(TestCase):
    """§17 #214: a long address wraps before its @, not inside "com"."""

    def test_the_filter_offers_one_break_and_escapes_the_rest(self):
        from core.templatetags.legal_tags import email_break
        self.assertEqual(email_break('a.b@c.uz'), 'a.b<wbr>@c.uz')
        self.assertEqual(email_break('<i>@c.uz'), '&lt;i&gt;<wbr>@c.uz')
        self.assertEqual(email_break('no-address'), 'no-address')

    def test_every_page_that_prints_the_address_offers_the_break(self):
        local, domain = legal.SELLER['email'].split('@')
        for path in ('/uz/contact/', '/ru/terms/', '/en/privacy/'):
            with self.subTest(path=path):
                self.assertIn(f'>{local}<wbr>@{domain}</a>', text(self.client, path))


class PruneCommandTests(SimpleTestCase):
    """The help says what the command filters on: when the cart was created."""

    def test_the_help_names_the_creation_date(self):
        from cart.management.commands.prune_guest_carts import Command
        self.assertIn('created', Command.help)
        self.assertNotIn('touched', Command.help)
