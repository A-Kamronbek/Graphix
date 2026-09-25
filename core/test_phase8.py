"""Phase 8: the legal documents and the copy around them.

Almost everything that can go wrong with a legal page is silent. A figure stops
matching the code it describes; a translation quietly loses a section; a page
promises something the checkout does not do. None of that raises. These tests
hold the three documents to the code they describe, and hold the three
languages of each document to each other (§17 #182, #183).
"""
import ast
import importlib.util
import re
from datetime import date
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.template import Context, Template
from core.runner import project_python_files
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format

from cart.models import Cart, CartItem
from core import legal
from payment.models import DeliveryOption, Order, PaymentOption

from .test_phase4 import make_product
from .test_phase6 import make_regions, make_user
from .test_phase7 import make_staff
from .test_phase12 import make_order

DOCS = ('terms', 'privacy', 'delivery')
LANGS = ('uz', 'ru', 'en')
PATHS = {'terms': 'terms', 'privacy': 'privacy', 'delivery': 'yetkazib-berish'}
TEMPLATES = Path(settings.BASE_DIR) / 'templates'


def body(doc, lang):
    """The source of one language of one document."""
    return (TEMPLATES / 'legal' / f'{doc}.{lang}.html').read_text(encoding='utf-8')


def page(client, doc, lang):
    """The rendered page, as text."""
    return client.get(f'/{lang}/{PATHS[doc]}/').content.decode()


def uz(name, *args):
    """An Uzbek URL, whatever language the previous request left active.

    ``LocaleMiddleware`` activates the language of each request and nothing
    deactivates it, so a bare ``reverse()`` after a request to /ru/ builds a
    Russian URL and the Uzbek assertions read a Russian page (§17 #124).
    """
    with translation.override('uz'):
        return reverse(name, args=args)


class DocumentPageTests(TestCase):
    """Each document, in each language, is a complete page."""

    def test_every_document_renders_in_every_language(self):
        for doc in DOCS:
            for lang in LANGS:
                with self.subTest(doc=doc, lang=lang):
                    response = self.client.get(f'/{lang}/{PATHS[doc]}/')
                    self.assertEqual(response.status_code, 200)
                    self.assertTemplateUsed(response, f'legal/{doc}.{lang}.html')

    def test_nothing_of_the_template_reaches_the_page(self):
        for doc in DOCS:
            for lang in LANGS:
                html = page(self.client, doc, lang)
                for token in ('{{', '{%', '{#', 'legal.seller', 'legal.'):
                    with self.subTest(doc=doc, lang=lang, token=token):
                        self.assertNotIn(token, html)

    def test_the_page_states_its_version_and_the_day_it_took_effect(self):
        version = legal.VERSIONS['terms'][0]
        with translation.override('uz'):
            html = page(self.client, 'terms', 'uz')
        self.assertIn(f'data-version="{version.number}"', html)
        self.assertIn(f'Tahrir {version.number} · 2026-yil 15-sentabrdan amalda', html)

    def test_the_history_lists_every_version_of_the_document(self):
        for doc in DOCS:
            html = page(self.client, doc, 'uz')
            rows = re.findall(r'<td data-label="Tahrir" class="num">([^<]+)</td>', html)
            with self.subTest(doc=doc):
                self.assertEqual(rows, [v.number for v in legal.VERSIONS[doc]])

    def test_the_contents_are_the_sections_printed_for_both_widths(self):
        """Read out of the text, so they cannot name a section it lacks
        (§17 #192) - and printed twice, once folded and once as a rail."""
        html = page(self.client, 'terms', 'uz')
        sections = re.findall(r'<section class="legal__sec" id="([^"]+)"', html)
        links = re.findall(r'<li><a href="#([^"]+)">', html)
        self.assertEqual(links, sections + sections)
        self.assertEqual(len(sections), 17)

    def test_a_translation_says_the_uzbek_text_prevails(self):
        for doc in DOCS:
            for lang in ('ru', 'en'):
                with self.subTest(doc=doc, lang=lang):
                    self.assertIn('data-precedence', body(doc, lang))

    def test_back_leads_to_our_own_page_and_never_off_site(self):
        ours = self.client.get('/uz/terms/', HTTP_REFERER='http://testserver/uz/signup/')
        self.assertContains(ours, 'href="http://testserver/uz/signup/"')
        theirs = self.client.get('/uz/terms/', HTTP_REFERER='https://example.com/x/')
        self.assertNotContains(theirs, 'example.com')


class LanguagesInStepTests(SimpleTestCase):
    """Three languages of one document are one document."""

    def test_every_language_has_the_same_sections_in_the_same_order(self):
        for doc in DOCS:
            seen = {lang: [anchor for anchor, _ in legal.contents(body(doc, lang))]
                    for lang in LANGS}
            with self.subTest(doc=doc):
                self.assertGreater(len(seen['uz']), 5)
                self.assertEqual(seen['ru'], seen['uz'])
                self.assertEqual(seen['en'], seen['uz'])

    def test_sections_are_numbered_one_by_one(self):
        for doc in DOCS:
            for lang in LANGS:
                headings = [title for _, title in legal.contents(body(doc, lang))]
                with self.subTest(doc=doc, lang=lang):
                    self.assertEqual([h.split('.')[0] for h in headings],
                                     [str(n) for n in range(1, len(headings) + 1)])

    def test_the_turned_comma_only_ever_builds_a_letter(self):
        """U+02BB is part of oʻ and gʻ; the glottal stop is U+02BC (§17 #130)."""
        for doc in DOCS:
            for lang in LANGS:
                text = body(doc, lang)
                strays = [text[m.start() - 5:m.end() + 5] for m in re.finditer('ʻ', text)
                          if text[m.start() - 1] not in 'oOgG']
                with self.subTest(doc=doc, lang=lang):
                    self.assertEqual(strays, [])

    def test_the_uzbek_text_uses_no_ascii_apostrophe_in_a_letter(self):
        for doc in DOCS:
            with self.subTest(doc=doc):
                self.assertEqual(re.findall(r"[oOgG]['‘’`]", body(doc, 'uz')), [])

    def test_no_price_or_period_is_typed_into_the_copy(self):
        """A figure typed into nine files is a figure that will disagree with
        the code (§17 #111). Prices come from the rows, periods from core.legal."""
        money = re.compile(r'\d[\d\s]*(?:&nbsp;)?\s*(?:soʻm|сум)')
        period = re.compile(r'(?<![\w{#-])\d+\s*(?:–\s*\d+\s*)?'
                            r'(?:kun|oy\b|daqiqa|дн|день|дня|дней|месяц|минут|day|month|minute)')
        for doc in DOCS:
            for lang in LANGS:
                text = body(doc, lang)
                with self.subTest(doc=doc, lang=lang):
                    self.assertEqual(money.findall(text), [])
                    self.assertEqual(period.findall(text), [])


class FiguresFollowTheCodeTests(TestCase):
    """Change the code and the page follows."""

    def tearDown(self):
        cache.clear()

    def test_delivery_prices_come_from_the_rows(self):
        DeliveryOption.objects.filter(code='uzpost_door').update(price=41000)
        cache.clear()      # the footer's tiers are cached for a minute
        for doc in ('terms', 'delivery'):
            with self.subTest(doc=doc):
                self.assertIn('41\xa0000', page(self.client, doc, 'uz'))

    def test_the_uncollected_fee_is_the_one_in_core_legal(self):
        with mock.patch.object(legal, 'UNCOLLECTED_FEE', 12345):
            for doc in ('terms', 'delivery'):
                with self.subTest(doc=doc):
                    self.assertIn('12\xa0345', page(self.client, doc, 'ru'))

    def test_the_payment_methods_are_the_ones_the_checkout_offers(self):
        html = page(self.client, 'terms', 'uz')
        self.assertIn('<strong>Click</strong>', html)
        self.assertNotIn('Naqd pul', html)
        PaymentOption.objects.filter(code='cash').update(is_active=True)
        self.assertIn('Naqd pul', page(self.client, 'terms', 'uz'))

    def test_the_guest_cart_age_is_the_prune_commands_default(self):
        from cart.management.commands.prune_guest_carts import Command
        parser = Command().create_parser('manage.py', 'prune_guest_carts')
        self.assertEqual(parser.get_default('days'), legal.facts().guest_cart_days)

    def test_the_code_window_is_the_one_the_signup_uses(self):
        from user import otp
        self.assertEqual(legal.facts().otp_minutes * 60, otp.TTL_SECONDS)
        self.assertEqual(legal.facts().otp_attempts, otp.MAX_ATTEMPTS)

    def test_the_review_limits_are_the_ones_the_form_enforces(self):
        from product import images, views
        facts = legal.facts()
        self.assertEqual(facts.review_photos, views.MAX_PHOTOS)
        self.assertEqual(facts.review_text, views.MAX_TEXT)
        self.assertEqual(facts.review_photo_mb * 1024 * 1024, images.MAX_BYTES)

    def test_the_session_lifetime_is_printed_from_settings(self):
        days = settings.SESSION_COOKIE_AGE // 86400
        self.assertIn(f'{days} kun amal qiladi', page(self.client, 'privacy', 'uz'))

    def test_cookies_the_policy_calls_a_year_live_no_longer(self):
        self.assertLessEqual(settings.CSRF_COOKIE_AGE, 366 * 86400)
        self.assertLessEqual(settings.LANGUAGE_COOKIE_AGE, 366 * 86400)

    def test_the_log_is_kept_for_the_period_the_policy_states(self):
        """Rotated by day, `LOG_RETENTION_DAYS` files kept (§17 #196)."""
        source = (Path(settings.BASE_DIR) / 'config' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn("'class': 'logging.handlers.TimedRotatingFileHandler'", source)
        self.assertIn("'backupCount': LOG_RETENTION_DAYS", source)
        self.assertEqual(legal.facts().log_days, settings.LOG_RETENTION_DAYS)


class RateLimitWindowTests(SimpleTestCase):
    """The privacy policy says the hashed IP counter lives an hour at most."""

    def test_no_limit_on_the_site_outlives_the_promise(self):
        from core.ratelimit import MAX_WINDOW
        windows = []
        for path, rel in project_python_files():
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, 'id', getattr(node.func, 'attr', ''))
                if name != 'is_rate_limited':
                    continue
                arg = node.args[3] if len(node.args) > 3 else next(
                    (k.value for k in node.keywords if k.arg == 'window'), None)
                self.assertIsNotNone(arg, f'{rel}:{node.lineno} has no window')
                value = eval(compile(ast.Expression(arg), rel, 'eval'), {}, {})
                windows.append((rel, node.lineno, value))
        self.assertGreaterEqual(len(windows), 10, 'the scan found too few calls to mean anything')
        too_long = [w for w in windows if w[2] > MAX_WINDOW]
        self.assertEqual(too_long, [])


class SellerDetailsTests(TestCase):
    """Who the offer is from, and nothing that was kept off the page."""

    def test_both_documents_name_the_seller_in_every_language(self):
        seller = legal.facts().seller
        for doc in ('terms', 'privacy'):
            for lang in LANGS:
                html = page(self.client, doc, lang)
                for value in (seller.registered_name, seller.email, seller.phone):
                    with self.subTest(doc=doc, lang=lang, value=value):
                        self.assertIn(value, html)

    def test_the_postal_address_is_in_the_offer_and_only_there(self):
        """§17 #226: the E-commerce Law wants an address in
        the offer (art. 16); nothing else on the site needs one, and the
        privacy policy links to the terms instead of repeating it."""
        seller = legal.facts().seller
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(seller.address, page(self.client, 'terms', lang))
                self.assertNotIn(seller.address, page(self.client, 'privacy', lang))

    def test_no_tax_number_or_bank_details_are_published(self):
        """§17 #184: name, address and contacts only."""
        for doc in DOCS:
            for lang in LANGS:
                html = page(self.client, doc, lang)
                for label in ('STIR', 'JSHSHIR', 'MFO', 'ИНН', 'ПИНФЛ', 'МФО',
                              'hisob raqami', 'расчётный счёт', 'IBAN'):
                    with self.subTest(doc=doc, lang=lang, label=label):
                        self.assertNotIn(label, html)

    def test_the_footer_and_the_contact_page_print_the_same_details(self):
        seller = legal.facts().seller
        for url in ('/uz/', '/uz/contact/'):
            html = self.client.get(url).content.decode()
            for fragment in (f'tel:{seller.phone_href}', f'mailto:{seller.email}',
                             seller.telegram_url):
                with self.subTest(url=url, fragment=fragment):
                    self.assertIn(fragment, html)

    def test_the_contact_page_names_the_seller(self):
        seller = legal.facts().seller
        html = self.client.get('/uz/contact/').content.decode()
        self.assertIn(seller.registered_name, html)
        # The address is not here any more (§17 #226); the link to the terms is.
        self.assertNotIn(seller.address, html)


class LinksToTheDocumentsTests(TestCase):
    """Footer, signup and checkout all lead to both documents (item 5)."""

    def test_the_privacy_policy_has_its_own_address_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(reverse('privacy'), f'/{lang}/privacy/')

    def test_the_footer_links_both_documents(self):
        html = self.client.get('/ru/').content.decode()
        self.assertIn('href="/ru/terms/"', html)
        self.assertIn('href="/ru/privacy/"', html)

    def test_the_signup_consent_links_both_and_asks_for_processing_consent(self):
        html = self.client.get('/uz/signup/').content.decode()
        label = html[html.index('<label class="check">'):]
        label = label[:label.index('</label>')]
        self.assertIn('href="/uz/terms/"', label)
        self.assertIn('href="/uz/privacy/"', label)
        self.assertIn('ishlov berilishiga rozilik beraman', label)

    def test_the_checkout_says_what_placing_the_order_accepts(self):
        user = make_user('shartlar', '+998901300001')
        _, variant = make_product('Oferta', stock=3)
        cart = Cart.objects.create(user=user, status=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1, price_stat=variant.price)
        self.client.force_login(user)
        html = self.client.get('/uz/checkout/').content.decode()
        self.assertIn('tugmasini bosib', html)
        self.assertIn('href="/uz/terms/"', html)
        self.assertIn('href="/uz/privacy/"', html)

    def test_the_sitemap_lists_the_privacy_policy_in_every_language(self):
        xml = self.client.get('/sitemap.xml').content.decode()
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(f'/{lang}/privacy/', xml)


class OrderPageTests(TestCase):
    """The confirmation screen states the rule in plain language (§19 Q11)."""

    def setUp(self):
        self.geo = make_regions()
        self.user = make_user('tasdiq', '+998901300002')
        _, variant = make_product('Tasdiq', stock=3)
        self.order = make_order(self.user, variant, status='paid')
        self.client.force_login(self.user)

    def _as(self, code, **fields):
        Order.objects.filter(pk=self.order.pk).update(
            delivery_option=DeliveryOption.objects.get(code=code),
            region=self.geo['tashkent'], district=self.geo['chilonzor'], **fields)
        return self.client.get(uz('order_detail', self.order.pk)).content.decode()

    # The label itself, not the words: the footer lists the delivery options,
    # and "Pochta boʻlimigacha" contains "Pochta boʻlimi" on every page.
    BRANCH = '<span class="label">Pochta boʻlimi</span>'
    ADDRESS = '<span class="label">Manzil</span>'

    def test_a_branch_order_states_the_hold_and_the_uncollected_rule(self):
        html = self._as('uzpost_office', postal_index='100011')
        facts = legal.facts()
        self.assertIn(self.BRANCH, html)
        self.assertNotIn(self.ADDRESS, html)
        self.assertIn(f'{facts.hold_months} oy saqlanadi', html)
        self.assertIn('15\xa0000 soʻm ushlab qolinadi', html)
        self.assertIn(f'{facts.refund_days} kun ichida', html)

    def test_a_home_order_is_not_called_a_post_office(self):
        """Every order has carried a region since §17 #106, and the page used
        `region_id` to decide - so a home address was labelled a branch."""
        html = self._as('uzpost_door', address='Amir Temur 1')
        self.assertNotIn(self.BRANCH, html)
        self.assertNotIn('ushlab qolinadi', html)
        self.assertIn(self.ADDRESS, html)

    def test_the_date_is_in_the_readers_language(self):
        """§18 #25: the Uzbek month list printed Uzbek to everyone.

        The page shows the local date, so the expectation is built from the
        local time too - from UTC it names the wrong day for the five hours
        after midnight in Tashkent, which is when this test first failed.
        """
        with translation.override('ru'):
            expected = date_format(timezone.localtime(self.order.created_at), 'j E Y')
            html = self.client.get(reverse('order_detail', args=[self.order.pk])).content.decode()
        self.assertIn(expected, html)


class DateHelperTests(SimpleTestCase):
    """The hand-made Uzbek month list is gone, and nothing still asks for it."""

    def test_the_module_is_gone(self):
        """Gone is gone, whether its package survived it or not.

        ``find_spec`` answers None when a module is missing from a package that
        exists, and RAISES when the package itself is missing. Both mean gone -
        but which one happens depends on whether an empty directory is lying
        around, and that differs by machine.

        It differed here. `payment/templatetags/` still existed, empty and
        untracked, on the machine this was written on: Python reads a directory
        with no ``__init__.py`` as a namespace package, so the call returned
        None and the test passed. On a fresh clone the directory is simply not
        there and the same call raises ``ModuleNotFoundError`` - which is what
        CI reported on its very first run, having never seen that leftover.

        The code was always right. The question was wrong.
        """
        try:
            spec = importlib.util.find_spec('payment.templatetags.uzb_dates')
        except ModuleNotFoundError:
            spec = None          # the whole package is absent: more gone, not less
        self.assertIsNone(spec)

    def test_no_template_loads_it(self):
        users = [p.name for p in TEMPLATES.rglob('*.html')
                 if 'uzb_dates' in p.read_text(encoding='utf-8')]
        self.assertEqual(users, [])

    def test_a_document_date_reads_as_each_language_writes_one(self):
        day = date(2026, 9, 15)
        tpl = Template('{% load legal_tags %}{{ d|legal_date }}')
        expected = {'uz': '2026-yil 15-sentabr', 'ru': '15 сентября 2026 г.',
                    'en': '15 September 2026'}
        for lang, text in expected.items():
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(tpl.render(Context({'d': day})), text)

    def test_a_range_is_one_unbreakable_value(self):
        """§17 #204: "1–" at the end of a line and "6 kunda" on the next."""
        tpl = Template('{% load legal_tags %}{{ a|legal_range:b }}')
        self.assertEqual(tpl.render(Context({'a': 1, 'b': 6})), '1\u2060–\u20606')

    def test_no_template_types_a_range_the_dash_can_break(self):
        typed = [p.name for p in TEMPLATES.rglob('*.html')
                 if re.search(r'\}\}\s*–\s*\{\{', p.read_text(encoding='utf-8'))]
        self.assertEqual(typed, [])

    def test_the_russian_noun_follows_its_number(self):
        from core.templatetags.legal_tags import ru_plural
        forms = 'день,дня,дней'
        for n, word in ((1, 'день'), (2, 'дня'), (5, 'дней'), (11, 'дней'), (14, 'дней'),
                        (21, 'день'), (22, 'дня'), (30, 'дней'), (112, 'дней')):
            with self.subTest(n=n):
                self.assertEqual(ru_plural(n, forms), word)


class OnTheWayLabelTests(TestCase):
    """Q26: the status says what the dashboard tile says (§17 #189)."""

    def test_the_label_in_three_languages(self):
        for lang, text in (('uz', 'Yetkazilmoqda'), ('ru', 'В доставке'), ('en', 'In transit')):
            with self.subTest(lang=lang), translation.override(lang):
                self.assertEqual(str(Order.Status.ON_THE_WAY.label), text)

    def test_the_stored_value_did_not_move(self):
        self.assertEqual(Order.Status.ON_THE_WAY.value, 'on_the_way')

    def test_the_timeline_and_the_heading_use_it(self):
        user = make_user('yolda', '+998901300003')
        _, variant = make_product('Holat', stock=3)
        order = make_order(user, variant, status='on_the_way')
        self.client.force_login(user)
        html = self.client.get(uz('order_status', order.pk)).content.decode()
        # The heading is the status, and the timeline's current step is it too.
        self.assertEqual(html.count('Yetkazilmoqda'), 2)
        self.assertNotIn('Yoʻlda', html)

    def test_the_tile_and_the_status_agree_in_russian(self):
        self.client.force_login(make_staff('plitka', '+998901300004'))
        html = self.client.get('/ru/boshqaruv/').content.decode()
        self.assertIn('В доставке', html)


class ProductCopyTemplateTests(TestCase):
    """Item 7: the description template, in the language of each box."""

    def test_each_box_gets_its_own_language_whatever_the_screen_is_in(self):
        from panel.catalogue import description_templates
        with translation.override('ru'):
            templates = description_templates()
        self.assertTrue(templates['description'].startswith('Dizayn:'))
        self.assertTrue(templates['description_ru'].startswith('Дизайн:'))
        self.assertTrue(templates['description_en'].startswith('Design:'))
        for text in templates.values():
            self.assertEqual(text.count('\n\n'), 3)

    def test_the_template_does_not_ask_again_for_what_has_a_field(self):
        """Fabric, weight and print method are in the spec strip (§17 #111)."""
        from panel.catalogue import description_templates
        for text in description_templates().values():
            for fact in ('g/m', 'GSM', '% ', 'DTF'):
                with self.subTest(fact=fact):
                    self.assertNotIn(fact, text)

    def test_the_panel_offers_it_beside_all_three_boxes(self):
        self.client.force_login(make_staff('tavsif', '+998901300005'))
        html = self.client.get('/uz/boshqaruv/mahsulotlar/yangi/').content.decode()
        for box in ('p-desc', 'p-desc-ru', 'p-desc-en'):
            with self.subTest(box=box):
                self.assertIn(f'data-copy-template="{box}"', html)
        self.assertIn('data-template="Дизайн:', html)


class ContactFormTests(TestCase):
    """The subject has the limit its column has - a sentence, not a 500."""

    def setUp(self):
        self.user = make_user('yozuvchi', '+998901300006')
        self.client.force_login(self.user)

    def test_a_subject_longer_than_the_column_is_refused(self):
        from core.models import Msg
        limit = Msg._meta.get_field('topic').max_length
        response = self.client.post('/uz/contact/', {'subject': 'a' * (limit + 1),
                                                     'message': 'Salom'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Msg.objects.exists())
        self.assertContains(response, 'a' * (limit + 1))

    def test_the_field_carries_the_same_limit(self):
        from core.models import Msg
        limit = Msg._meta.get_field('topic').max_length
        self.assertContains(self.client.get('/uz/contact/'), f'maxlength="{limit}"')


class AboutPageTests(TestCase):
    """Item 6: the About page says only what the shop does."""

    def test_it_renders_in_every_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(self.client.get(f'/{lang}/about/').status_code, 200)

    def test_the_same_day_warehouse_promise_is_gone(self):
        html = self.client.get('/uz/about/').content.decode()
        self.assertNotIn('bugunoq', html)
        self.assertNotIn('Toshkentda, omborda', html)
