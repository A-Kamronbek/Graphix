"""Phase 21: the owner's third round, and the fault behind the first item.

Four things the developer brought on 2026-10-14. A home order whose address
came from the map was refused with its region, district and street empty,
though the page showed all three. Payme, switched on with its keys, failed.
Payme had no mark at the checkout. And an unpaid order could be cancelled
only from its status page, which a customer had to find first.

Each class is one of those, written as what a customer sees or as what the
gateway is asked for.
"""
import base64
import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse

from payment import services
from payment.models import PAYMENT_LOGOS, Order, PaymentOption

from .test_phase16 import CheckoutCase, order_of

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

    def test_nothing_in_the_sheet_sends_the_form_by_itself(self):
        """Its buttons close it. Only the order button places the order."""
        html = self.client.get(reverse('checkout')).content.decode()
        sheet = html.split('data-address-sheet ', 1)[1].split('data-address-sheet-body', 1)[0]
        tail = html.split('data-address-sheet-body', 1)[1].split('</form>', 1)[0]
        for part in (sheet, tail):
            for tag in re.findall(r'<button[^>]*>', part):
                with self.subTest(tag=tag):
                    self.assertIn('type="button"', tag)

    def test_an_order_from_the_map_with_its_fields_sent_is_placed(self):
        """What the form sends now that the fields go with it."""
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
