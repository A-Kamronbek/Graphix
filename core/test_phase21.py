"""Phase 21: the owner's third round, and the fault behind the first item.

Four things the developer brought on 2026-10-14. A home order whose address
came from the map was refused with its region, district and street empty,
though the page showed all three. Payme, switched on with its keys, failed.
Payme had no mark at the checkout. And an unpaid order could be cancelled
only from its status page, which a customer had to find first.

Each class is one of those, written as what a customer sees or as what the
gateway is asked for.

Then a fifth, asked the same day: an order nobody paid for waited forever.
It is cancelled now three days after it was placed (§17 #373). And a sixth:
the checkout starts with the account's own name and number (§17 #374).
"""
import base64
import copy
import json
import re
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from panel.models import AUTO_CANCEL_NOTE, OrderStatusChange
from payment import services
from payment.models import PAYMENT_LOGOS, Order, PaymentOption

from .test_phase7 import make_staff
from .test_phase16 import CheckoutCase, order_of, stock_of

#: A Payme cashbox id has this shape: 24 hex digits. Not a real one.
PAYME_ID = '5e730e8e0b852a417aa49ceb'
PAYME_KEY = 'test-key-for-the-suite'


def payme_settings():
    """The settings a shop with Payme's keys in `.env` runs with."""
    tolov = copy.deepcopy(settings.TOLOV)
    tolov['PAYME'].update(PAYME_ID=PAYME_ID, PAYME_KEY=PAYME_KEY)
    return override_settings(PAYME_ID=PAYME_ID, PAYME_KEY=PAYME_KEY, TOLOV=tolov)


def link_params(link):
    """What a Payme link asks for, read back out of it: ``{'m': ..., 'a': ...}``."""
    encoded = urlsplit(link).path.lstrip('/')
    text = base64.b64decode(encoded).decode('utf-8')
    return dict(part.split('=', 1) for part in text.split(';'))


def checkout_form(html):
    """The checkout's own form, from its opening tag to its closing one."""
    start = html.index('data-checkout')
    return html[start:html.index('</form>', start)]


class AddressSheetTests(CheckoutCase):
    """The sheet the map's fields are moved into is part of the form.

    The fields themselves are moved by the script, which no test here runs;
    what it moves them into is markup, and markup is what decides whether a
    field is sent. The whole flow was driven in a browser as well, with a
    stand-in for Google's script, before and after.
    """

    def test_the_sheet_is_inside_the_checkout_form(self):
        html = self.client.get(reverse('checkout')).content.decode()
        form = checkout_form(html)
        self.assertIn('data-address-sheet ', form)
        self.assertIn('data-address-sheet-body', form)
        # And only once on the page: a second sheet outside would be where
        # the script put the fields.
        self.assertEqual(html.count('data-address-sheet-body'), 1)

    def test_no_button_in_the_sheet_sends_the_form(self):
        """Its buttons close it. Enter in its one-line field closes it too,
        which `checkout.js` does and the browser check covered."""
        html = self.client.get(reverse('checkout')).content.decode()
        sheet = html.split('data-address-sheet ', 1)[1].split('data-address-sheet-body', 1)[0]
        tail = html.split('data-address-sheet-body', 1)[1].split('</form>', 1)[0]
        for part in (sheet, tail):
            for tag in re.findall(r'<button[^>]*>', part):
                with self.subTest(tag=tag):
                    self.assertIn('type="button"', tag)

    def test_an_order_from_the_map_with_its_fields_sent_is_placed(self):
        """What the form sends now that the fields go with it.

        The server's side only: it always took such an order. The test that
        would have caught the fault is the one above, on where the sheet is.
        """
        response = self.post(delivery_option='uzpost_door', postal_index=None,
                             address="O'zbekiston shoh ko'chasi 9", address_source='map',
                             latitude='41.311100', longitude='69.279700')
        order = Order.objects.get()
        self.assertRedirects(response, reverse('payment', args=[order.pk]),
                             fetch_redirect_response=False)
        self.assertEqual((order.region_id, order.district_id),
                         (self.geo['tashkent'].pk, self.geo['chilonzor'].pk))
        self.assertEqual(order.address, "O'zbekiston shoh ko'chasi 9")
        self.assertEqual(order.address_source, 'map')


@payme_settings()
class PaymeLinkTests(CheckoutCase):
    """What Payme is asked for: the order's total, in tiyin, once."""

    def payme_order(self, total):
        """An order placed for Payme, of ``total`` so'm."""
        order = order_of(self.user, (self.shirt_m, 1))
        order.payment_method = Order.PaymentMethod.PAYME
        order.total_price = total
        order.save()
        # As the pay button reads it: a Decimal, from the database.
        order.refresh_from_db()
        return order

    def test_the_link_asks_for_the_total_in_tiyin(self):
        for total in (1000, 149000, 369000):
            with self.subTest(total=total):
                order = self.payme_order(total)
                params = link_params(services.generate_paylink(order, 'https://graphix.uz/'))
                self.assertEqual(params['a'], str(total * 100))
                self.assertEqual(params['ac.order_id'], str(order.pk))
                self.assertEqual(params['m'], PAYME_ID)
                order.delete()

    def test_the_link_goes_to_paymes_own_checkout(self):
        link = services.generate_paylink(self.payme_order(1000), 'https://graphix.uz/')
        self.assertEqual(urlsplit(link).netloc, 'checkout.paycom.uz')

    def ask_payme_check(self, order_id, amount):
        """Payme's first question about an order, as Payme sends it."""
        body = {'method': 'CheckPerformTransaction', 'id': 1,
                'params': {'amount': int(amount), 'account': {'order_id': str(order_id)}}}
        token = base64.b64encode(('Paycom:%s' % PAYME_KEY).encode()).decode()
        return self.client.post(reverse('payme_webhook'), json.dumps(body),
                                content_type='application/json',
                                HTTP_AUTHORIZATION='Basic ' + token).json()

    def test_payme_is_told_yes_for_the_sum_the_link_asked_for(self):
        """The link and the callback agree, which is the point of the fix.

        Payme checks the order with the shop before it charges a card, and
        the shop compares the sum with `total_price` in tiyin. The link used
        to ask for a hundred times that, and every check would have failed.
        """
        order = self.payme_order(1000)
        params = link_params(services.generate_paylink(order, 'https://graphix.uz/'))
        answer = self.ask_payme_check(params['ac.order_id'], params['a'])
        self.assertEqual(answer.get('result'), {'allow': True}, answer)
        wrong = self.ask_payme_check(order.pk, int(params['a']) * 100)
        self.assertNotIn('result', wrong)
        self.assertEqual(wrong['error']['code'], -31001)


class PaymeMarkTests(CheckoutCase):
    """Payme's mark before its name, as Click's and Telegram's are."""

    def test_it_is_named_and_its_file_is_a_drawing_that_runs_nothing(self):
        spec = PAYMENT_LOGOS['payme']
        self.assertEqual((spec['width'], spec['height']), (24, 24))
        drawing = Path(finders.find(spec['src'])).read_text(encoding='utf-8')
        self.assertTrue(drawing.lstrip().startswith('<svg'))
        self.assertIn('#25E8FF', drawing)       # Payme's cyan
        for word in ('<script', 'href', 'onload', '<text', '<image'):
            with self.subTest(word=word):
                self.assertNotIn(word, drawing)

    def test_it_stands_before_payme_at_the_checkout(self):
        PaymentOption.objects.filter(code='payme').update(is_active=True)
        html = self.client.get(reverse('checkout')).content.decode()
        label = html.split('name="payment_method" value="payme"', 1)[1].split('</label>', 1)[0]
        tag = re.search(r'<img class="pay__mark"[^>]*>', label).group(0)
        self.assertIn('img/pay/payme', tag)
        self.assertIn('alt=""', tag)
        self.assertLess(label.index('pay__mark'), label.index('<strong>Payme</strong>'))


class CancelOnOrderPageTests(CheckoutCase):
    """An unpaid order can be cancelled from its own page, under the pay button."""

    def page(self, order):
        return self.client.get(reverse('order_detail', args=[order.pk])).content.decode()

    def test_the_button_is_under_the_pay_button(self):
        order = order_of(self.user, (self.shirt_m, 1))
        html = self.page(order)
        pay = html.index('href="%s"' % reverse('payment', args=[order.pk]))
        cancel = html.index('action="%s"' % reverse('order_cancel', args=[order.pk]))
        self.assertLess(pay, cancel)
        form = html[cancel:].split('</form>', 1)[0]
        self.assertIn('csrfmiddlewaretoken', form)
        self.assertIn('Buyurtmani bekor qilish', form)

    def test_pressing_it_cancels_the_order(self):
        order = order_of(self.user, (self.shirt_m, 1))
        response = self.client.post(reverse('order_cancel', args=[order.pk]))
        self.assertRedirects(response, reverse('order_status', args=[order.pk]),
                             fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_an_order_that_is_not_waiting_has_no_such_button(self):
        for status in (Order.Status.PAID, Order.Status.CANCELLED, Order.Status.DONE):
            with self.subTest(status=status):
                order = order_of(self.user, (self.shirt_m, 1), status=status)
                html = self.page(order)
                self.assertNotIn(reverse('order_cancel', args=[order.pk]), html)
                self.assertNotIn('Buyurtmani bekor qilish', html)

    def test_it_reads_in_each_language(self):
        order = order_of(self.user, (self.shirt_m, 1))
        for lang, words in (('ru', 'Отменить заказ'), ('en', 'Cancel order')):
            with self.subTest(lang=lang):
                from django.utils import translation
                with translation.override(lang):
                    address = reverse('order_detail', args=[order.pk])
                self.assertContains(self.client.get(address), words)


class UnpaidOrdersCancelTests(CheckoutCase):
    """An order still unpaid three days after it was placed is cancelled."""

    def aged(self, days, hours=0, **fields):
        """An order placed ``days`` days and ``hours`` hours ago."""
        order = order_of(self.user, (self.shirt_m, 1), **fields)
        placed = timezone.now() - timedelta(days=days, hours=hours)
        # `created_at` is auto_now_add, so it is set after the fact.
        Order.objects.filter(pk=order.pk).update(created_at=placed)
        return order

    def run_job(self, *args):
        """The daily job, as the timer runs it; what it printed."""
        out = StringIO()
        call_command('cancel_unpaid_orders', *args, stdout=out)
        return out.getvalue()

    def status(self, order):
        order.refresh_from_db()
        return order.status

    def test_three_days_is_the_line(self):
        self.assertEqual(services.UNPAID_ORDER_DAYS, 3)
        old = self.aged(3, hours=1)
        young = self.aged(2, hours=23)
        printed = self.run_job()
        self.assertEqual(self.status(old), Order.Status.CANCELLED)
        self.assertEqual(self.status(young), Order.Status.PAYING)
        self.assertIn(old.order_no, printed)
        self.assertNotIn(young.order_no, printed)

    def test_an_order_that_is_a_sale_is_never_touched(self):
        for status in (Order.Status.PAID, Order.Status.PROCESSING,
                       Order.Status.ON_THE_WAY, Order.Status.DONE):
            with self.subTest(status=status):
                order = self.aged(30, status=status)
                self.run_job()
                self.assertEqual(self.status(order), status)

    def test_a_cash_order_waits_for_its_door(self):
        """Paid when the parcel is handed over, so unpaid is not abandoned."""
        order = self.aged(10)
        Order.objects.filter(pk=order.pk).update(payment_method=Order.PaymentMethod.CASH)
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.PAYING)

    def test_a_telegram_order_goes_as_any_other(self):
        order = self.aged(4)
        Order.objects.filter(pk=order.pk).update(payment_method=Order.PaymentMethod.TELEGRAM)
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.CANCELLED)

    def test_the_move_is_in_the_trail_by_nobody(self):
        order = self.aged(5)
        self.run_job()
        change = OrderStatusChange.objects.get(order=order)
        self.assertEqual((change.from_status, change.to_status),
                         (Order.Status.PAYING, Order.Status.CANCELLED))
        self.assertIsNone(change.changed_by)
        self.assertEqual(change.note, AUTO_CANCEL_NOTE)
        self.assertTrue(change.is_automatic)

    def test_the_panel_says_avtomatik_and_not_a_deleted_account(self):
        order = self.aged(5)
        self.run_job()
        self.client.force_login(make_staff())
        html = self.client.get(reverse('panel_order', args=[order.order_no])).content.decode()
        trail = html.split('class="trail"', 1)[1]
        self.assertIn('avtomatik', trail)
        self.assertNotIn('oʻchirilgan hisob', trail)

    def test_a_row_with_no_author_and_another_note_is_still_a_deleted_account(self):
        order = self.aged(5)
        change = OrderStatusChange.objects.create(
            order=order, from_status='paying', to_status='paid', note='Django admin')
        self.assertFalse(change.is_automatic)

    def test_nothing_is_given_back_because_nothing_was_held(self):
        before = stock_of(self.shirt_m)
        self.aged(5)
        self.run_job()
        self.assertEqual(stock_of(self.shirt_m), before)

    def test_a_second_run_changes_nothing_and_writes_nothing(self):
        order = self.aged(5)
        self.run_job()
        printed = self.run_job()
        self.assertEqual(OrderStatusChange.objects.filter(order=order).count(), 1)
        self.assertIn('Cancelled 0 ', printed)

    def test_a_dry_run_lists_and_changes_nothing(self):
        order = self.aged(5)
        printed = self.run_job('--dry-run')
        self.assertIn(order.order_no, printed)
        self.assertIn('1 unpaid order(s) older than 3 days', printed)
        self.assertEqual(self.status(order), Order.Status.PAYING)
        self.assertFalse(OrderStatusChange.objects.exists())

    def test_days_can_be_given_but_not_nought(self):
        order = self.aged(5)
        self.run_job('--days', '7')
        self.assertEqual(self.status(order), Order.Status.PAYING)
        with self.assertRaises(CommandError):
            self.run_job('--days', '0')
        self.assertEqual(self.status(order), Order.Status.PAYING)

    def test_an_order_paid_after_the_list_was_read_is_not_cancelled(self):
        """The row is asked again, locked, before anything is moved."""
        order = self.aged(5)
        real = services.stale_unpaid_orders

        class PaidOnceListed:
            """The job's list, with a payment landing the moment it is read."""

            def __init__(self, *args, **kwargs):
                self.stale = real(*args, **kwargs)

            def values_list(self, *args, **kwargs):
                listed = list(self.stale.values_list(*args, **kwargs))
                services.apply_successful_payment(order)
                return listed

            def select_for_update(self):
                return self.stale.select_for_update()

        with mock.patch('panel.management.commands.cancel_unpaid_orders.stale_unpaid_orders',
                        PaidOnceListed):
            printed = self.run_job()
        self.assertIn('Cancelled 0 ', printed)
        self.assertEqual(self.status(order), Order.Status.PAID)
        self.assertFalse(OrderStatusChange.objects.filter(to_status='cancelled').exists())

    def test_the_timer_runs_this_command_daily(self):
        units = Path(settings.BASE_DIR) / 'deploy' / 'systemd'
        service = (units / 'graphix-cancel-unpaid.service').read_text(encoding='utf-8')
        timer = (units / 'graphix-cancel-unpaid.timer').read_text(encoding='utf-8')
        self.assertIn('manage.py cancel_unpaid_orders\n', service)
        self.assertIn('User=graphix', service)
        self.assertIn('OnCalendar=*-*-* 04:40:00 Asia/Tashkent', timer)
        self.assertIn('Persistent=true', timer)
        self.assertIn('Unit=graphix-cancel-unpaid.service', timer)


class ContactPrefillTests(CheckoutCase):
    """The checkout opens with the account's name and number, both editable."""

    def field_value(self, html, name):
        """The ``value`` the page gives the input called ``name``."""
        tag = re.search(r'<input[^>]*name="%s"[^>]*>' % name, html).group(0)
        return re.search(r'value="([^"]*)"', tag).group(1)

    def opened(self):
        return self.client.get(reverse('checkout')).content.decode()

    def test_the_name_and_the_number_are_the_accounts(self):
        self.user.first_name = 'Dilnoza'
        self.user.last_name = 'Karimova'
        self.user.save()
        html = self.opened()
        self.assertEqual(self.field_value(html, 'name'), 'Dilnoza Karimova')
        # As the field shows a number: the nine digits after its +998.
        self.assertEqual(self.field_value(html, 'phone'), '90 122 00 03')

    def test_a_first_name_alone_is_the_name(self):
        self.user.first_name = 'Dilnoza'
        self.user.save()
        self.assertEqual(self.field_value(self.opened(), 'name'), 'Dilnoza')

    def test_no_name_given_leaves_the_field_blank(self):
        """Not "Xaridor", and not the username, which is the number again."""
        self.assertEqual(self.user.first_name, '')
        html = self.opened()
        self.assertEqual(self.field_value(html, 'name'), '')
        self.assertEqual(self.field_value(html, 'phone'), '90 122 00 03')

    def test_what_was_typed_comes_back_and_not_the_accounts(self):
        """A form sent back to be put right shows the customer's own words."""
        self.user.first_name = 'Dilnoza'
        self.user.save()
        response = self.post(name='Aziza Rahimova', phone='93 555 66 77', region=None)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(self.field_value(html, 'name'), 'Aziza Rahimova')
        self.assertEqual(self.field_value(html, 'phone'), '93 555 66 77')

    def test_an_order_is_placed_with_what_the_form_sends(self):
        self.user.first_name = 'Dilnoza'
        self.user.save()
        self.post(name='Aziza Rahimova', phone='93 555 66 77')
        order = Order.objects.get()
        self.assertEqual(order.recipient_name, 'Aziza Rahimova')
        self.assertEqual(order.phone, '+998 93 555 66 77')
