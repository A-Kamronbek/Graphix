"""Phase 20: paying through the shop's admin, and a chart for the rest.

A gateway that cannot take a payment leaves the shop with no way to be paid.
"Telegram admin orqali" is the way round it: the order is placed as any other
and waits, the customer is sent to a Telegram chat with the shop's admin with
the message already written, and staff mark the order paid in the panel when
the money has come. Nothing about it is automatic, and that is the point of
it: there is nothing in it to break.

The second half is the four products the owner's size chart did not reach.

Each class is one of those, written as what a customer or a member of staff
sees.
"""
import importlib
import re
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core import telegram
from core.middleware import PAY_PAGES
from panel.models import OrderStatusChange
from panel.services import set_status
from payment import services
from payment.models import PAYMENT_LOGOS, Order, PaymentOption
from product.models import (Category, Colour, Product, Size, SizeChart, SizeChartRow,
                            Variant)

from .test_phase6 import make_user
from .test_phase7 import make_staff
from .test_phase16 import CheckoutCase, order_of, stock_of

ROOT = Path(settings.BASE_DIR)
ADMIN = 'VMShopSupport'


def models_at(app, migration):
    """The models as they stood once ``migration`` had run: what a migration is handed."""
    return MigrationLoader(connection).project_state((app, migration)).apps


def link_in(html):
    """The address of the button that opens Telegram, or None when there is none."""
    found = re.search(r'<a class="btn btn--primary[^"]*" href="(https://t\.me/[^"]*)"', html)
    return found.group(1).replace('&amp;', '&') if found else None


def text_of(link):
    """The message a Telegram link carries, as the customer will see it written."""
    return parse_qs(urlsplit(link).query)['text'][0]


@override_settings(TELEGRAM_PAY_ADMIN=ADMIN)
class TelegramOrderCase(CheckoutCase):
    """A customer with an order placed for Telegram and not yet paid for.

    The admin's name is set here and not read from the machine the tests run
    on, where a developer may have put another in `.env`.
    """

    def setUp(self):
        super().setUp()
        self.order = order_of(self.user, (self.shirt_m, 2), delivery=25000)
        self.order.payment_method = Order.PaymentMethod.TELEGRAM
        self.order.recipient_name = 'Dilnoza Karimova'
        self.order.save()

    def page(self, order=None, language='uz'):
        """The pay page of ``order``, read in ``language``."""
        with translation.override(language):
            address = reverse('payment', args=[(order or self.order).pk])
        return self.client.get(address)


class TelegramOptionTests(CheckoutCase):
    """The method as the checkout offers it."""

    def test_it_is_offered_after_the_gateways_and_before_cash(self):
        row = PaymentOption.objects.get(code='telegram')
        self.assertTrue(row.is_active)
        self.assertEqual(row.name, 'Telegram admin orqali')
        self.assertTrue(row.name_ru)
        self.assertTrue(row.name_en)
        # The name is all the checkout says about it (the developer's word).
        self.assertEqual((row.note, row.note_ru, row.note_en), ('', '', ''))
        PaymentOption.objects.update(is_active=True)
        self.assertEqual(list(PaymentOption.objects.values_list('code', flat=True)),
                         ['click', 'payme', 'octo', 'telegram', 'cash'])

    def test_every_row_a_customer_can_choose_is_a_method_an_order_can_hold(self):
        for code in PaymentOption.objects.values_list('code', flat=True):
            with self.subTest(code=code):
                self.assertIn(code, Order.PaymentMethod.values)

    def test_it_stands_at_the_checkout_with_telegrams_mark_before_its_name(self):
        html = self.client.get(reverse('checkout')).content.decode()
        label = html.split('name="payment_method" value="telegram"', 1)[1].split('</label>', 1)[0]
        tag = re.search(r'<img class="pay__mark"[^>]*>', label).group(0)
        self.assertIn('img/pay/telegram', tag)
        self.assertIn('alt=""', tag)
        self.assertLess(label.index('pay__mark'),
                        label.index('<strong>Telegram admin orqali</strong>'))

    def test_its_row_carries_the_name_and_nothing_under_it(self):
        html = self.client.get(reverse('checkout')).content.decode()
        label = html.split('name="payment_method" value="telegram"', 1)[1].split('</label>', 1)[0]
        self.assertNotIn('field__hint', label)
        # Click keeps its note.
        click = html.split('name="payment_method" value="click"', 1)[1].split('</label>', 1)[0]
        self.assertIn('field__hint', click)

    def test_the_mark_is_a_drawing_that_runs_and_fetches_nothing(self):
        drawing = Path(finders.find(PAYMENT_LOGOS['telegram']['src'])).read_text(encoding='utf-8')
        self.assertTrue(drawing.lstrip().startswith('<svg'))
        for word in ('<script', 'href', 'onload', '<text'):
            with self.subTest(word=word):
                self.assertNotIn(word, drawing)

    def test_with_two_methods_offered_neither_is_chosen_for_the_customer(self):
        html = self.client.get(reverse('checkout')).content.decode()
        radios = re.findall(r'<input type="radio" name="payment_method"[^>]*>', html)
        self.assertEqual(len(radios), 2)
        self.assertFalse([radio for radio in radios if 'checked' in radio])

    def test_alone_it_is_chosen_already(self):
        PaymentOption.objects.exclude(code='telegram').update(is_active=False)
        html = self.client.get(reverse('checkout')).content.decode()
        radios = re.findall(r'<input type="radio" name="payment_method"[^>]*>', html)
        self.assertEqual(len(radios), 1)
        self.assertIn('checked', radios[0])

    def test_an_order_placed_with_it_waits_and_lands_on_its_pay_page(self):
        before = stock_of(self.shirt_m)
        response = self.post(payment_method='telegram')
        order = Order.objects.get()
        self.assertEqual(order.payment_method, Order.PaymentMethod.TELEGRAM)
        self.assertEqual(order.status, Order.Status.PAYING)
        self.assertRedirects(response, reverse('payment', args=[order.pk]),
                             fetch_redirect_response=False)
        # Not paid for, so it holds no stock, as any unpaid order holds none.
        self.assertEqual(stock_of(self.shirt_m), before)

    def test_switched_off_it_cannot_be_ordered_with(self):
        PaymentOption.objects.filter(code='telegram').update(is_active=False)
        response = self.post(payment_method='telegram')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())


class TelegramPayPageTests(TelegramOrderCase):
    """The page the customer is sent to Telegram from."""

    def test_the_button_opens_a_chat_with_the_admin(self):
        html = self.page().content.decode()
        link = link_in(html)
        self.assertIsNotNone(link)
        address = urlsplit(link)
        self.assertEqual((address.scheme, address.netloc, address.path),
                         ('https', 't.me', '/' + ADMIN))
        self.assertEqual(list(parse_qs(address.query)), ['text'])
        tag = re.search(r'<a class="btn btn--primary[^>]*>', html).group(0)
        # In a tab of its own, so the order stays open in this one, and the
        # other site is told nothing about the page it was opened from.
        self.assertIn('target="_blank"', tag)
        self.assertIn('rel="noopener noreferrer"', tag)

    def test_the_message_says_what_is_to_be_paid_for(self):
        text = text_of(link_in(self.page().content.decode()))
        self.assertEqual(text.split('\n'), [
            'Assalomu alaykum! GRAPHIX saytidagi buyurtmam uchun toʻlov qilmoqchiman.',
            '',
            'Buyurtma raqami: %s' % self.order.order_no,
            'Summa: 325 000 soʻm',
            'Ism: Dilnoza Karimova',
            'Telefon: %s' % self.order.phone,
        ])
        self.assertRegex(self.order.order_no, r'^GX-\d{6}-\d{4}$')

    def test_the_sum_is_the_orders_total_with_ordinary_spaces(self):
        self.order.total_price = 1234567
        self.order.save()
        text = text_of(link_in(self.page().content.decode()))
        self.assertIn('Summa: 1 234 567 soʻm', text)
        self.assertNotIn('\u00a0', text)

    def test_the_message_is_in_the_language_of_the_page(self):
        russian = text_of(link_in(self.page(language='ru').content.decode()))
        self.assertIn('Хочу оплатить заказ', russian)
        self.assertIn('Номер заказа: %s' % self.order.order_no, russian)
        self.assertIn('Сумма: 325 000 сум', russian)
        english = text_of(link_in(self.page(language='en').content.decode()))
        self.assertIn('Order number: %s' % self.order.order_no, english)
        self.assertIn('Total: 325 000 soʻm', english)

    def test_a_name_cannot_write_its_own_address(self):
        """What the customer typed is carried as text and as nothing else."""
        self.order.recipient_name = 'A&text=boshqa#x ?start=1\nB "qq7" <b>'
        self.order.save()
        html = self.page().content.decode()
        link = link_in(html)
        address = urlsplit(link)
        self.assertEqual((address.netloc, address.path, address.fragment),
                         ('t.me', '/' + ADMIN, ''))
        self.assertEqual(link.count('?'), 1)
        self.assertNotIn('&', link)
        self.assertIn('Ism: A&text=boshqa#x ?start=1\nB "qq7" <b>', text_of(link))
        # And nothing typed reaches the page as markup.
        self.assertNotIn('<b>', html)
        self.assertNotIn('"qq7"', html)

    def test_an_order_with_no_recipient_uses_the_accounts_name_or_none(self):
        self.order.recipient_name = ''
        self.order.save()
        self.user.first_name = 'Dilnoza'
        self.user.save()
        self.assertIn('Ism: Dilnoza', text_of(link_in(self.page().content.decode())))
        self.user.first_name = ''
        self.user.save()
        self.assertNotIn('Ism:', text_of(link_in(self.page().content.decode())))

    def test_the_page_says_what_happens_and_names_the_admin_for_who_cannot_open_it(self):
        html = self.page().content.decode()
        self.assertIn('Telegram orqali toʻlov', html)
        self.assertIn('Telegram orqali adminga bogʻlanib, toʻlovni amalga oshiring. '
                      'Admin buyurtmangiz uchun toʻlovni tasdiqlaydi.', html)
        self.assertIn('Telegramda yozish', html)
        # A screen reader is told the button leaves this tab.
        self.assertIn('<span class="sr-only">(yangi oynada ochiladi)</span>', html)
        self.assertIn('<strong>@%s</strong>' % ADMIN, html)
        self.assertIn('<strong>%s</strong>' % self.order.order_no, html)

    def test_there_is_no_gateway_to_be_sent_to(self):
        """A link and not a form: the policy names no Telegram host, and needs none."""
        response = self.page()
        html = response.content.decode()
        self.assertNotIn(reverse('payment_start', args=[self.order.pk]), html)
        self.assertNotIn('Toʻlovga oʻtish', html)
        self.assertFalse([host for host in PAY_PAGES if 't.me' in host or 'telegram' in host])
        self.assertNotIn('t.me', response.headers['Content-Security-Policy'])
        self.assertNotIn(Order.PaymentMethod.TELEGRAM, services.GATEWAY_CREDENTIALS)

    def test_no_note_for_whoever_reads_the_template_reaches_the_page(self):
        html = self.page().content.decode()
        self.assertNotIn('{#', html)
        self.assertNotIn('{% comment', html)
        self.assertNotIn('No gateway', html)

    def test_the_customer_can_still_cancel_or_read_the_order(self):
        html = self.page().content.decode()
        self.assertIn(reverse('order_cancel', args=[self.order.pk]), html)
        self.assertIn(reverse('order_detail', args=[self.order.pk]), html)

    def test_pressing_start_by_hand_goes_nowhere_outside_the_site(self):
        response = self.client.post(reverse('payment_start', args=[self.order.pk]))
        self.assertRedirects(response, reverse('order_status', args=[self.order.pk]),
                             fetch_redirect_response=False)
        with self.assertRaises(services.PaymentMethodUnavailable):
            services.generate_paylink(self.order, 'https://graphix.uz/')

    def test_an_order_no_longer_waiting_has_nothing_to_write_about(self):
        for status in (Order.Status.PAID, Order.Status.CANCELLED):
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(status=status)
                response = self.page()
                self.assertRedirects(response, reverse('order_status', args=[self.order.pk]),
                                     fetch_redirect_response=False)

    def test_another_customers_order_is_not_there(self):
        other = make_user('boshqa', '+998901220009')
        theirs = order_of(other, (self.hoodie_m, 1))
        theirs.payment_method = Order.PaymentMethod.TELEGRAM
        theirs.save()
        self.assertEqual(self.page(theirs).status_code, 404)

    def test_signed_out_there_is_no_page(self):
        self.client.logout()
        response = self.page()
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('t.me', response.headers['Location'])


class TelegramAdminNameTests(TelegramOrderCase):
    """Who the customer is sent to, and what happens when it is nobody."""

    def test_the_name_is_read_with_or_without_its_at(self):
        for typed in (ADMIN, '@' + ADMIN, '  %s  ' % ADMIN):
            with self.subTest(typed=typed), override_settings(TELEGRAM_PAY_ADMIN=typed):
                self.assertEqual(services.telegram_admin(), ADMIN)
                self.assertTrue(services.method_is_configured('telegram'))

    def test_what_is_not_a_telegram_name_is_nobody(self):
        """A name is put into an address, so only a name is let through."""
        for typed in ('', None, 'ab', '1shop', 'two words', 'shop/../x', 'shop?x=1',
                      'https://t.me/shop', 'shop.name', '@@shop', 'x' * 33, 'doʻkon'):
            with self.subTest(typed=typed), override_settings(TELEGRAM_PAY_ADMIN=typed):
                self.assertEqual(services.telegram_admin(), '')
                self.assertEqual(services.telegram_pay_link(self.order), '')
                self.assertFalse(services.method_is_configured('telegram'))

    @override_settings(TELEGRAM_PAY_ADMIN='')
    def test_with_nobody_to_write_to_the_page_says_so_and_offers_no_button(self):
        response = self.page()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIsNone(link_in(html))
        self.assertNotIn('text=', html)
        self.assertIn('Hozircha toʻlov usuli mavjud emas', html)
        # And somewhere to go for the customer who cannot pay this way.
        self.assertIn('href="%s"' % reverse('contact'), html.split('msg--warn', 1)[1].split('</p>', 1)[0])
        # The order can still be cancelled from here.
        self.assertIn(reverse('order_cancel', args=[self.order.pk]), html)

    def test_the_panel_shows_whether_there_is_somebody(self):
        self.client.force_login(make_staff())
        rows = {row.code: row for row in
                self.client.get(reverse('panel_settings')).context['payments']}
        self.assertTrue(rows['telegram'].configured)
        with override_settings(TELEGRAM_PAY_ADMIN=''):
            rows = {row.code: row for row in
                    self.client.get(reverse('panel_settings')).context['payments']}
            self.assertFalse(rows['telegram'].configured)


class StaffMarkItPaidTests(TelegramOrderCase):
    """The other half: the order is paid when staff say the money has come."""

    def test_marking_it_paid_takes_the_stock_and_records_who_did(self):
        staff = make_staff()
        before = stock_of(self.shirt_m)
        change = set_status(self.order, Order.Status.PAID, by=staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(stock_of(self.shirt_m), before - 2)
        self.assertEqual((change.from_status, change.to_status, change.changed_by),
                         (Order.Status.PAYING, Order.Status.PAID, staff))

    def test_marking_it_paid_tells_the_shop_once_it_has_committed(self):
        """The one message a gateway's payment sends, for a sale staff record."""
        with mock.patch.object(telegram, 'deliver') as sent:
            with self.captureOnCommitCallbacks(execute=False) as queued:
                set_status(self.order, Order.Status.PAID, by=make_staff())
            sent.assert_not_called()
            for callback in queued:
                callback()
        self.assertEqual(sent.call_count, 1)
        event, text = sent.call_args.args[:2]
        self.assertEqual(event, 'order.paid')
        self.assertIn(self.order.order_no, text)
        self.assertIn('Telegram admin orqali', text)

    def test_moving_a_sale_along_tells_nobody_again(self):
        staff = make_staff()
        set_status(self.order, Order.Status.PAID, by=staff)
        with mock.patch.object(telegram, 'notify_paid_order') as told:
            set_status(self.order, Order.Status.PROCESSING, by=staff)
            set_status(self.order, Order.Status.ON_THE_WAY, by=staff)
            set_status(self.order, Order.Status.DONE, by=staff)
        told.assert_not_called()

    def test_a_move_that_fails_tells_nobody(self):
        with mock.patch.object(telegram, 'deliver') as sent, \
                mock.patch.object(OrderStatusChange.objects, 'create', side_effect=RuntimeError):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    set_status(self.order, Order.Status.PAID, by=make_staff())
        sent.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAYING)

    def test_the_panel_offers_paid_for_an_order_that_waits(self):
        self.client.force_login(make_staff())
        response = self.client.get(reverse('panel_orders'), {'method': 'telegram'})
        self.assertEqual([order.pk for order in response.context['orders']], [self.order.pk])
        self.assertIn(('telegram', 'Telegram admin orqali'),
                      [(value, str(label)) for value, label in response.context['methods']])
        self.assertIn(Order.Status.PAID, response.context['settable_values'])
        self.assertContains(response, 'Telegram admin orqali')

    def test_the_customer_cannot_mark_it_paid(self):
        """Nothing a customer can send moves the order: only cancelling is theirs."""
        self.client.post(reverse('payment_start', args=[self.order.pk]))
        self.page()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAYING)


class OtherMethodsTests(TelegramOrderCase):
    """The pay page of every other method is as it was."""

    def by(self, method):
        """The pay page of the order, as if it had been placed with ``method``."""
        Order.objects.filter(pk=self.order.pk).update(payment_method=method)
        return self.page().content.decode()

    def test_a_click_order_still_has_its_button_and_its_heading(self):
        html = self.by('click')
        self.assertRegex(html, r'<h1 class="h1">\s*Click orqali toʻlov\s*</h1>')
        self.assertIn('action="%s"' % reverse('payment_start', args=[self.order.pk]), html)
        self.assertIn('Toʻlovga oʻtish', html)
        self.assertIsNone(link_in(html))
        self.assertNotIn('t.me/' + ADMIN, html)

    def test_the_heading_names_the_method_the_order_was_placed_with(self):
        for method, name in (('payme', 'Payme'), ('octo', 'Octo')):
            with self.subTest(method=method):
                self.assertRegex(self.by(method),
                                 r'<h1 class="h1">\s*%s orqali toʻlov\s*</h1>' % name)

    def test_the_heading_reads_in_each_language(self):
        Order.objects.filter(pk=self.order.pk).update(payment_method='click')
        self.assertRegex(self.page(language='ru').content.decode(),
                         r'<h1 class="h1">\s*Оплата через Click\s*</h1>')
        self.assertRegex(self.page(language='en').content.decode(),
                         r'<h1 class="h1">\s*Pay with Click\s*</h1>')


class PhoneFieldTests(CheckoutCase):
    """The checkout's phone field has +998 in it, and the customer types the rest."""

    def field(self, html):
        """The phone field's frame, from its opening to its closing tag."""
        return html.split('<label class="tel"', 1)[1].split('</label>', 1)[0]

    def test_the_code_is_written_in_the_field(self):
        html = self.client.get(reverse('checkout')).content.decode()
        field = self.field(html)
        self.assertIn('for="id_phone"', field)
        self.assertIn('<span class="tel__code">+998</span>', field)
        tag = re.search(r'<input[^>]*name="phone"[^>]*>', field).group(0)
        self.assertIn('placeholder="90 123 45 67"', tag)
        self.assertIn('autocomplete="tel-national"', tag)
        self.assertIn('inputmode="tel"', tag)
        self.assertIn('required', tag)
        self.assertIn('value=""', tag)

    def test_the_rest_of_the_number_is_enough(self):
        for typed in ('90 122 00 03', '901220003', '90-122-00-03'):
            with self.subTest(typed=typed):
                Order.objects.all().delete()
                self.cart.status = True
                self.cart.save(update_fields=['status'])
                self.post(phone=typed)
                self.assertEqual(Order.objects.get().phone, '+998 90 122 00 03')

    def test_a_number_typed_or_pasted_whole_is_read_the_same(self):
        for typed in ('+998901220003', '+998 90 122 00 03', '998901220003'):
            with self.subTest(typed=typed):
                Order.objects.all().delete()
                self.cart.status = True
                self.cart.save(update_fields=['status'])
                self.post(phone=typed)
                self.assertEqual(Order.objects.get().phone, '+998 90 122 00 03')

    def test_a_number_that_is_not_one_is_refused(self):
        for typed in ('12345', '90 122 00', '+7 900 122 00 03', '\u0669\u0660\u0661\u0662\u0662\u0660\u0660\u0660\u0663'):
            with self.subTest(typed=typed):
                response = self.post(phone=typed)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Order.objects.exists())
                self.assertIn('format: +998 XX XXX XX XX', self.said(response))

    def test_shown_again_it_is_the_rest_of_the_number(self):
        """A form sent back for another reason keeps the number, without +998 twice."""
        response = self.post(phone='+998901220003', name='')
        self.assertFalse(Order.objects.exists())
        tag = re.search(r'<input[^>]*name="phone"[^>]*>', response.content.decode()).group(0)
        self.assertIn('value="90 122 00 03"', tag)


class PhoneFieldEverywhereTests(TestCase):
    """Every phone field on the storefront has +998 in it (§17 #367)."""

    def setUp(self):
        from .test_phase15 import catch_sms
        self.inbox = catch_sms(self)

    def field(self, html):
        """The phone field's frame, from its opening to its closing tag."""
        return html.split('<label class="tel"', 1)[1].split('</label>', 1)[0]

    def tag(self, html):
        """The phone input itself."""
        return re.search(r'<input[^>]*name="phone"[^>]*>', self.field(html)).group(0)

    def test_both_doors_have_it(self):
        for door in ('login', 'signup'):
            with self.subTest(door=door):
                html = self.client.get(reverse(door)).content.decode()
                field = self.field(html)
                self.assertIn('<span class="tel__code">+998</span>', field)
                tag = self.tag(html)
                self.assertIn('placeholder="90 123 45 67"', tag)
                self.assertIn('autofocus', tag)
                self.assertIn('autocomplete="tel-national"', tag)
                self.assertIn('value=""', tag)
                # The old hint, which asked for +998 to be typed, is gone.
                self.assertNotIn('+998 ...', html)

    def test_no_phone_field_is_left_without_it(self):
        """Every template that asks for a phone asks for it through the one partial."""
        for path in sorted((ROOT / 'templates').rglob('*.html')):
            text = path.read_text(encoding='utf-8')
            if 'type="tel"' in text:
                with self.subTest(file=str(path.relative_to(ROOT))):
                    self.assertEqual(path.name, '_tel.html')

    def test_the_rest_of_the_number_signs_in(self):
        from .test_phase15 import customer
        user = customer('+998 90 777 66 55')
        self.client.post(reverse('login'), {'phone': '90 777 66 55'})
        self.client.post(reverse('verify_phone'), {'code': self.inbox.code})
        self.assertEqual(self.client.session.get('_auth_user_id'), str(user.pk))

    def test_a_number_carried_from_the_other_door_shows_once(self):
        """The link from one door to the other carries the whole number."""
        response = self.client.get(reverse('signup') + '?phone=%2B998901112233')
        self.assertIn('value="90 111 22 33"', self.tag(response.content.decode()))

    def test_a_refused_number_comes_back_as_typed_and_says_why(self):
        response = self.client.post(reverse('login'), {'phone': '12345'})
        html = response.content.decode()
        tag = self.tag(html)
        self.assertIn('value="12345"', tag)
        self.assertIn('aria-describedby="id_phone_error"', tag)
        self.assertIn('id="id_phone_error"', html)
        self.assertIn('field--error', html.split('<label class="tel"', 1)[0].rsplit('<div', 1)[1])


class NationalFilterTests(SimpleTestCase):
    """What a field that shows +998 itself is filled with."""

    def test_a_whole_number_in_any_form_comes_out_as_the_rest(self):
        from core.templatetags.phone_tags import national
        for value in ('+998 90 123 45 67', '+998901234567', '998901234567', '901234567',
                      '90-123-45-67'):
            with self.subTest(value=value):
                self.assertEqual(national(value), '90 123 45 67')

    def test_anything_else_is_shown_as_it_came(self):
        from core.templatetags.phone_tags import national
        for value in ('12345', '+7 900 123 45 67', 'abc'):
            with self.subTest(value=value):
                self.assertEqual(national(value), value)
        self.assertEqual(national(None), '')
        self.assertEqual(national(''), '')


class TelegramSeedTests(TestCase):
    """What the migration that adds the row does to a shop that has one already."""

    def setUp(self):
        self.migration = importlib.import_module('payment.migrations.0027_seed_telegram_option')
        self.models = models_at('payment', '0026_telegram_method')

    def test_a_row_the_owner_changed_is_left_as_he_left_it(self):
        PaymentOption.objects.filter(code='telegram').update(
            name='Telegram', is_active=False, sort_order=1)
        self.migration.forwards(self.models, None)
        row = PaymentOption.objects.get(code='telegram')
        self.assertEqual((row.name, row.is_active, row.sort_order), ('Telegram', False, 1))

    def test_it_adds_the_row_where_there_is_none_and_takes_it_away_again(self):
        PaymentOption.objects.filter(code='telegram').delete()
        self.migration.forwards(self.models, None)
        row = PaymentOption.objects.get(code='telegram')
        self.assertEqual((row.name, row.is_active, row.sort_order),
                         ('Telegram admin orqali', True, 16))
        self.migration.backwards(self.models, None)
        self.assertFalse(PaymentOption.objects.filter(code='telegram').exists())
        self.assertTrue(PaymentOption.objects.filter(code='click').exists())


class ChartForTheRestTests(TestCase):
    """The products the owner's chart did not reach take it, where that is safe."""

    def setUp(self):
        self.migration = importlib.import_module('product.migrations.0029_chart_for_the_rest')
        SizeChart.objects.all().delete()
        self.chart = SizeChart.objects.create(name='Futbolka')
        self.sizes = {}
        for label in ('S', 'M', 'L'):
            self.sizes[label] = (Size.objects.filter(size=label).first()
                                 or Size.objects.create(size=label))
            SizeChartRow.objects.create(chart=self.chart, size=self.sizes[label],
                                        chest_cm='110.0', length_cm='70.0')
        self.colour = Colour.objects.create(colour='Qora')

    def product(self, name, *labels, **fields):
        """A product made in the sizes ``labels``."""
        product = Product.objects.create(name=name, **fields)
        for label in labels:
            size = self.sizes.get(label) or Size.objects.create(size=label)
            Variant.objects.create(product=product, size=size, colour=self.colour,
                                   price=150000, available=True, stock=3)
        return product

    def run_it(self):
        """Run it as `migrate` does: on the models of the migration before it."""
        self.migration.attach(models_at('product', '0028_owner_size_chart'), None)

    def chart_of(self, product):
        """The chart ``product`` points at itself, read from the database."""
        product.refresh_from_db()
        return product.size_chart_id

    def test_a_product_with_no_chart_takes_the_shops(self):
        bare = self.product('Ghost Bite', 'S', 'M', 'L')
        in_a_category = self.product('SWAG', 'M', category=Category.objects.create(name='Erkaklar'))
        self.run_it()
        self.assertEqual(self.chart_of(bare), self.chart.pk)
        self.assertEqual(self.chart_of(in_a_category), self.chart.pk)
        self.assertEqual(bare.resolve_size_chart(), self.chart)

    def test_a_product_that_reaches_a_chart_through_its_category_is_left(self):
        category = Category.objects.create(name='Futbolkalar', size_chart=self.chart)
        product = self.product('Chrome Bite', 'S', category=category)
        self.run_it()
        self.assertIsNone(self.chart_of(product))
        self.assertEqual(product.resolve_size_chart(), self.chart)

    def test_a_product_in_a_size_the_chart_does_not_have_is_left(self):
        cap = self.product('Kepka', 'Bir oʻlcham')
        mixed = self.product('Xudi', 'M', 'XXL')
        self.run_it()
        self.assertIsNone(self.chart_of(cap))
        self.assertIsNone(self.chart_of(mixed))

    def test_a_product_made_in_no_size_yet_is_left(self):
        empty = self.product('Yangi')
        self.run_it()
        self.assertIsNone(self.chart_of(empty))

    def test_with_two_charts_in_the_shop_nothing_is_chosen_for_anybody(self):
        other = SizeChart.objects.create(name='Xudi')
        bare = self.product('Ed Hardy', 'S')
        on_other = self.product('Keng', 'S', size_chart=other)
        self.run_it()
        self.assertIsNone(self.chart_of(bare))
        self.assertEqual(self.chart_of(on_other), other.pk)

    def test_with_no_chart_in_the_shop_nothing_happens(self):
        SizeChart.objects.all().delete()
        bare = self.product('Ed Hardy', 'S')
        self.run_it()
        self.assertIsNone(self.chart_of(bare))

    def test_run_again_it_changes_nothing(self):
        bare = self.product('Ghost Bite', 'S', 'M')
        left_out = self.product('Kepka', 'Bir oʻlcham')
        self.run_it()
        first = (self.chart_of(bare), self.chart_of(left_out))
        self.run_it()
        self.assertEqual((self.chart_of(bare), self.chart_of(left_out)), first)
        self.assertEqual(first, (self.chart.pk, None))
        self.assertEqual(SizeChart.objects.count(), 1)


class TemplateCommentTests(SimpleTestCase):
    """A note in a template that runs over two lines is printed on the page.

    Django ends a ``{# #}`` note at the end of its line, so one that goes on
    to a second line is not a note at all, and the visitor reads it. A note
    of more than one line is a ``{% comment %}`` block.
    """

    def test_every_short_note_closes_on_the_line_it_opens(self):
        for path in sorted((ROOT / 'templates').rglob('*.html')):
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if '{#' in line:
                    with self.subTest(file=str(path.relative_to(ROOT)), line=number):
                        self.assertIn('#}', line[line.index('{#'):])


class SettingTests(SimpleTestCase):
    """The admin's name is a setting with a default, and not a secret."""

    def test_the_shop_has_somebody_to_write_to_without_a_line_in_env(self):
        source = (ROOT / 'config' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn('TELEGRAM_PAY_ADMIN = os.environ.get("TELEGRAM_PAY_ADMIN", "%s")' % ADMIN,
                      source)

    def test_the_example_env_says_what_the_line_is(self):
        example = (ROOT / '.env.example').read_text(encoding='utf-8')
        self.assertIn('# TELEGRAM_PAY_ADMIN=%s' % ADMIN, example)
