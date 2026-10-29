"""Payme's Merchant API, answered by the shop itself (§17 #421).

Payme's sandbox at test.paycom.uz runs two scenarios against the endpoint
before Payme switches a cashbox on, and each class below starts with the
steps it takes, in its order and with the answers it expects
(developer.help.paycom.uz, "Песочница"). Then what the protocol asks beyond
the sandbox, and the faults tolov had, each written as the call Payme makes
and what the shop must answer.

The calls go through the URL, with CSRF checks on, as Payme's would: a
gateway has no CSRF token (§17 #270).
"""
import base64
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from tolov.integrations.django.models import PaymentTransaction

from payment import payme
from payment.models import Order

from .test_phase4 import make_product
from .test_phase6 import make_user
from .test_phase16 import order_of, stock_of

KEY = 'test-key-for-the-suite'
PAYME_ID = '5e730e8e0b852a417aa49ceb'


def signed(key=KEY):
    """The ``Authorization`` header Payme sends: ``Paycom`` and the cashbox key."""
    return 'Basic ' + base64.b64encode(('Paycom:%s' % key).encode()).decode()


def ms(moment):
    return int(moment.timestamp() * 1000)


@override_settings(PAYME_ID=PAYME_ID, PAYME_KEY=KEY)
class PaymeCase(TestCase):
    """An order of one shirt, 150 000 so'm, placed for Payme and awaiting payment."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = make_user()
        _product, self.variant = make_product('Dizayn', stock=5)
        self.order = self.payme_order()
        self.tiyin = int(self.order.total_price) * 100

    def payme_order(self, **changes):
        order = order_of(self.user, (self.variant, 1))
        order.payment_method = Order.PaymentMethod.PAYME
        for name, value in changes.items():
            setattr(order, name, value)
        order.save()
        return order

    def call(self, method, params, *, auth=None, raw=None):
        """Post one call as Payme does; the parsed answer."""
        body = raw if raw is not None else json.dumps(
            {'jsonrpc': '2.0', 'id': 2032, 'method': method, 'params': params})
        response = self.client.post(reverse('payme_webhook'), body,
                                    content_type='application/json',
                                    HTTP_AUTHORIZATION=auth or signed())
        self.assertEqual(response.status_code, 200)
        return response.json()

    def account(self, order=None, **params):
        order = order or self.order
        return {'amount': int(order.total_price) * 100, 'account': {'order_id': order.pk}, **params}

    def create(self, payme_id, order=None, at=None):
        return self.call('CreateTransaction', self.account(
            order, id=payme_id, time=ms(at or timezone.now())))

    def code(self, answer):
        self.assertNotIn('result', answer, answer)
        return answer['error']['code']

    def result(self, answer):
        self.assertNotIn('error', answer, answer)
        return answer['result']

    def order_status(self):
        return Order.objects.get(pk=self.order.pk).status


class SandboxScenarioOneTests(PaymeCase):
    """Payme's first scenario: a transaction created, then cancelled unperformed."""

    def test_a_wrong_key_is_not_allowed_for_any_method(self):
        for method in payme.METHODS:
            with self.subTest(method=method):
                answer = self.call(method, self.account(id='a' * 24), auth=signed('wrong'))
                self.assertEqual(self.code(answer), -32504)

    def test_a_wrong_amount(self):
        wrong = dict(self.account(), amount=self.tiyin + 100)
        self.assertEqual(self.code(self.call('CheckPerformTransaction', wrong)), -31001)
        wrong.update(id='a' * 24, time=ms(timezone.now()))
        self.assertEqual(self.code(self.call('CreateTransaction', wrong)), -31001)

    def test_an_order_that_is_not_there(self):
        missing = {'amount': self.tiyin, 'account': {'order_id': 999999}}
        for method, params in (('CheckPerformTransaction', missing),
                               ('CreateTransaction', dict(missing, id='a' * 24,
                                                          time=ms(timezone.now())))):
            with self.subTest(method=method):
                error = self.call(method, params)['error']
                self.assertTrue(-31099 <= error['code'] <= -31050, error)
                self.assertEqual(error['data'], 'order_id')

    def test_create_repeat_check_refuse_a_second_then_cancel(self):
        self.assertEqual(self.result(self.call('CheckPerformTransaction', self.account())),
                         {'allow': True})
        first = self.result(self.create('A' * 24))
        self.assertEqual(first['state'], 1)
        # Asked again, the same answer.
        self.assertEqual(self.result(self.create('A' * 24)), first)
        self.assertEqual(self.result(self.call('CheckTransaction', {'id': 'A' * 24}))['state'], 1)
        # A new transaction for the order that is awaiting payment.
        self.assertEqual(self.code(self.create('B' * 24)), -31008)
        cancelled = self.result(self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 3}))
        self.assertEqual(cancelled['state'], -1)
        self.assertGreater(cancelled['cancel_time'], 0)
        checked = self.result(self.call('CheckTransaction', {'id': 'A' * 24}))
        self.assertEqual((checked['state'], checked['reason']), (-1, 3))


class SandboxScenarioTwoTests(PaymeCase):
    """Payme's second scenario: created, performed, then cancelled (a refund)."""

    def test_create_perform_twice_then_refund(self):
        self.assertEqual(self.result(self.call('CheckPerformTransaction', self.account())),
                         {'allow': True})
        created = self.result(self.create('A' * 24))
        self.assertEqual(self.result(self.create('A' * 24)), created)
        self.assertEqual(self.code(self.create('B' * 24)), -31008)

        performed = self.result(self.call('PerformTransaction', {'id': 'A' * 24}))
        self.assertEqual(performed['state'], 2)
        self.assertEqual(performed['transaction'], created['transaction'])
        self.assertEqual(self.result(self.call('PerformTransaction', {'id': 'A' * 24})), performed)
        self.assertEqual(self.order_status(), Order.Status.PAID)
        self.assertEqual(stock_of(self.variant), 4)

        checked = self.result(self.call('CheckTransaction', {'id': 'A' * 24}))
        self.assertEqual((checked['state'], checked['perform_time']), (2, performed['perform_time']))

        with mock.patch('core.telegram.notify_refund') as told:
            refunded = self.result(self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 5}))
        self.assertEqual(refunded['state'], -2)
        self.assertEqual(self.result(self.call('CheckTransaction', {'id': 'A' * 24}))['state'], -2)
        # The order stays a sale, its stock taken, and the shop is told.
        self.assertEqual(self.order_status(), Order.Status.PAID)
        self.assertEqual(stock_of(self.variant), 4)
        told.assert_called_once()
        self.assertEqual(told.call_args.args[0].pk, self.order.pk)


class ProtocolTests(PaymeCase):
    """What the protocol asks that the sandbox does not show, and tolov's faults."""

    def test_an_unknown_transaction_is_not_found_not_a_wrong_amount(self):
        for method, params in (('PerformTransaction', {'id': 'X' * 24}),
                               ('CheckTransaction', {'id': 'X' * 24}),
                               ('CancelTransaction', {'id': 'X' * 24, 'reason': 3})):
            with self.subTest(method=method):
                self.assertEqual(self.code(self.call(method, params)), -31003)

    def test_a_cancelled_transaction_is_never_performed(self):
        """tolov performed it, and the order it was for read paid."""
        self.create('A' * 24)
        self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 3})
        self.assertEqual(self.code(self.call('PerformTransaction', {'id': 'A' * 24})), -31008)
        self.assertEqual(self.code(self.create('A' * 24)), -31008)
        self.assertEqual(self.order_status(), Order.Status.PAYING)
        self.assertEqual(stock_of(self.variant), 5)

    def test_a_cancel_before_performing_leaves_the_order_to_be_paid_again(self):
        """As a failed Click payment does (§17 #396): the customer may try again."""
        self.create('A' * 24)
        self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 2})
        self.assertEqual(self.order_status(), Order.Status.PAYING)
        self.assertEqual(self.result(self.call('CheckPerformTransaction', self.account())),
                         {'allow': True})
        self.assertEqual(self.result(self.create('B' * 24))['state'], 1)

    def test_an_order_already_paid_is_not_paid_for_again(self):
        """tolov said yes to it, and a second transaction would have been opened."""
        self.create('A' * 24)
        self.call('PerformTransaction', {'id': 'A' * 24})
        for method, params in (('CheckPerformTransaction', self.account()),
                               ('CreateTransaction', self.account(id='B' * 24,
                                                                  time=ms(timezone.now())))):
            with self.subTest(method=method):
                error = self.call(method, params)['error']
                self.assertEqual((error['code'], error['data']), (-31051, 'order_id'))

    def test_a_cancelled_order_is_not_paid_for(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.CANCELLED)
        error = self.call('CheckPerformTransaction', self.account())['error']
        self.assertEqual(error['code'], -31051)

    def test_an_order_placed_for_another_method_is_not_paymes(self):
        Order.objects.filter(pk=self.order.pk).update(payment_method=Order.PaymentMethod.CLICK)
        self.assertEqual(self.code(self.call('CheckPerformTransaction', self.account())), -31051)

    def test_check_perform_says_no_while_another_transaction_is_open(self):
        self.create('A' * 24)
        self.assertEqual(self.code(self.call('CheckPerformTransaction', self.account())), -31008)

    def test_a_transaction_past_twelve_hours_is_cancelled_not_performed(self):
        thirteen_ago = timezone.now() - timedelta(hours=13)
        PaymentTransaction.objects.create(
            gateway=PaymentTransaction.PAYME, transaction_id='A' * 24,
            account_id=str(self.order.pk), amount=Decimal('150000'), state=1,
            extra_data={'time': ms(thirteen_ago)})
        self.assertEqual(self.code(self.call('PerformTransaction', {'id': 'A' * 24})), -31008)
        checked = self.result(self.call('CheckTransaction', {'id': 'A' * 24}))
        self.assertEqual((checked['state'], checked['reason']), (-1, 4))
        self.assertEqual(self.order_status(), Order.Status.PAYING)

    def test_an_expired_transaction_is_answered_with_a_refusal_when_created_again(self):
        thirteen_ago = timezone.now() - timedelta(hours=13)
        PaymentTransaction.objects.create(
            gateway=PaymentTransaction.PAYME, transaction_id='A' * 24,
            account_id=str(self.order.pk), amount=Decimal('150000'), state=1,
            extra_data={'time': ms(thirteen_ago)})
        self.assertEqual(self.code(self.create('A' * 24, at=thirteen_ago)), -31008)
        self.assertEqual(PaymentTransaction.objects.get(transaction_id='A' * 24).state, -1)
        # An expired one does not hold the order: a new transaction is opened.
        self.assertEqual(self.result(self.create('B' * 24))['state'], 1)

    def test_a_transaction_created_more_than_twelve_hours_ago_is_not_opened(self):
        late = timezone.now() - timedelta(hours=13)
        self.assertEqual(self.code(self.create('A' * 24, at=late)), -31008)
        self.assertFalse(PaymentTransaction.objects.filter(transaction_id='A' * 24).exists())

    def test_an_account_error_speaks_three_languages_and_names_its_field(self):
        error = self.call('CheckPerformTransaction',
                          {'amount': self.tiyin, 'account': {'order_id': 999999}})['error']
        self.assertEqual(set(error['message']), {'ru', 'uz', 'en'})
        self.assertEqual(error['message']['uz'], 'Buyurtma topilmadi.')
        self.assertEqual(error['message']['ru'], 'Заказ не найден.')
        self.assertEqual(error['message']['en'], 'Order not found.')
        self.assertEqual(error['data'], 'order_id')

    def test_every_message_is_written_in_each_language(self):
        for name in ('NOT_ALLOWED', 'UNREADABLE', 'MALFORMED', 'NO_METHOD', 'SYSTEM',
                     'WRONG_AMOUNT', 'NO_TRANSACTION', 'CANNOT', 'NO_ORDER', 'NOT_PAYABLE'):
            words = payme.localised(getattr(payme, name)[1])
            with self.subTest(name=name):
                self.assertNotEqual(words['ru'], words['uz'])
                self.assertNotEqual(words['en'], words['uz'])

    def test_the_answer_echoes_the_request_id(self):
        answer = self.call('CheckPerformTransaction', self.account())
        self.assertEqual(answer['id'], 2032)
        refused = self.call('CheckPerformTransaction', self.account(), auth=signed('wrong'))
        self.assertEqual(refused['id'], 2032)

    def test_a_broken_call(self):
        self.assertEqual(self.code(self.call(None, None, raw='{not json')), -32700)
        self.assertEqual(self.code(self.call(None, None, raw='[1, 2]')), -32600)
        self.assertEqual(self.code(self.call(None, None, raw=json.dumps(
            {'id': 1, 'method': 'CheckTransaction', 'params': 'id'}))), -32600)
        answer = self.call('ChangePassword', {'password': 'x'})
        self.assertEqual((answer['error']['code'], answer['error']['data']),
                         (-32601, 'ChangePassword'))
        self.assertEqual(self.code(self.call('CancelTransaction', {'id': 'A' * 24})), -32600)

    def test_a_failure_inside_is_a_system_error_not_a_500(self):
        with mock.patch.object(payme, 'METHODS', {'CheckTransaction': mock.Mock(side_effect=RuntimeError)}):
            self.assertEqual(self.code(self.call('CheckTransaction', {'id': 'A' * 24})), -32400)

    def test_the_transaction_is_the_shops_own_number_and_stays_it(self):
        created = self.result(self.create('A' * 24))
        tx = PaymentTransaction.objects.get(transaction_id='A' * 24)
        self.assertEqual(created['transaction'], str(tx.pk))
        self.assertEqual(created['create_time'], ms(tx.created_at))
        self.assertEqual(tx.account_id, str(self.order.pk))
        self.assertEqual(tx.amount, Decimal('150000'))

    def test_the_amount_is_compared_with_the_frozen_total(self):
        """A promo code's order costs its total, and no other sum pays it."""
        cheaper = self.payme_order(total_price=Decimal('135000'), discount=Decimal('15000'))
        self.assertEqual(self.result(self.call('CheckPerformTransaction', self.account(cheaper))),
                         {'allow': True})
        full = dict(self.account(cheaper), amount=15000000)
        self.assertEqual(self.code(self.call('CheckPerformTransaction', full)), -31001)

    def test_an_account_written_as_text_is_read(self):
        params = {'amount': self.tiyin, 'account': {'order_id': str(self.order.pk)}}
        self.assertEqual(self.result(self.call('CheckPerformTransaction', params)), {'allow': True})


class StatementTests(PaymeCase):
    """GetStatement: Payme's list for a reconciliation."""

    def test_by_paymes_time_in_its_order_with_every_field(self):
        now = timezone.now()
        other = self.payme_order()
        self.create('A' * 24, at=now - timedelta(minutes=10))
        self.call('PerformTransaction', {'id': 'A' * 24})
        self.create('B' * 24, order=other, at=now - timedelta(minutes=5))
        self.call('CancelTransaction', {'id': 'B' * 24, 'reason': 3})
        listed = self.result(self.call('GetStatement', {
            'from': ms(now - timedelta(minutes=20)), 'to': ms(now)}))['transactions']
        self.assertEqual([t['id'] for t in listed], ['A' * 24, 'B' * 24])
        first = listed[0]
        self.assertEqual(set(first), {'id', 'time', 'amount', 'account', 'create_time',
                                      'perform_time', 'cancel_time', 'transaction', 'state',
                                      'reason', 'receivers'})
        self.assertEqual(first['time'], ms(now - timedelta(minutes=10)))
        self.assertEqual(first['amount'], self.tiyin)
        self.assertEqual(first['account'], {'order_id': self.order.pk})
        self.assertEqual((first['state'], listed[1]['state'], listed[1]['reason']), (2, -1, 3))
        self.assertEqual(first['transaction'],
                         str(PaymentTransaction.objects.get(transaction_id='A' * 24).pk))

    def test_the_bounds_are_paymes_times_both_included(self):
        at = timezone.now() - timedelta(minutes=10)
        self.create('A' * 24, at=at)
        for bounds, found in (((ms(at), ms(at)), 1), ((ms(at) + 1, ms(at) + 60000), 0),
                              ((ms(at) - 60000, ms(at) - 1), 0)):
            with self.subTest(bounds=bounds):
                listed = self.result(self.call('GetStatement', {'from': bounds[0], 'to': bounds[1]}))
                self.assertEqual(len(listed['transactions']), found)

    def test_a_refused_create_is_not_listed(self):
        self.create('A' * 24)
        self.create('B' * 24)            # refused: A is open for the order
        listed = self.result(self.call('GetStatement', {'from': 0, 'to': ms(timezone.now()) + 1000}))
        self.assertEqual([t['id'] for t in listed['transactions']], ['A' * 24])


class EndpointTests(PaymeCase):
    """The address Payme is given, and what it says to anything else."""

    def test_it_is_unprefixed_and_post_only(self):
        self.assertEqual(reverse('payme_webhook'), '/payment/payme/update/')
        self.assertEqual(self.client.get(reverse('payme_webhook')).status_code, 405)

    @override_settings(PAYME_KEY='')
    def test_without_the_key_it_answers_503_and_says_why(self):
        with self.assertLogs('payment.views', 'ERROR'):
            response = self.client.post(reverse('payme_webhook'), '{}',
                                        content_type='application/json')
        self.assertEqual(response.status_code, 503)

    def test_an_unsigned_call_marks_nothing_paid(self):
        response = self.client.post(reverse('payme_webhook'), json.dumps(
            {'id': 1, 'method': 'PerformTransaction', 'params': {'id': 'A' * 24}}),
            content_type='application/json')
        self.assertEqual(response.json()['error']['code'], -32504)
        self.assertEqual(self.order_status(), Order.Status.PAYING)

    def test_the_answer_is_json_rpc(self):
        answer = self.call('CheckPerformTransaction', self.account())
        self.assertEqual(answer['jsonrpc'], '2.0')


class RefundNoticeTests(PaymeCase):
    """A refund of a paid order tells the shop, in Uzbek, with the order's link."""

    def test_the_notice(self):
        from core import telegram
        self.create('A' * 24)
        self.call('PerformTransaction', {'id': 'A' * 24})
        order = Order.objects.get(pk=self.order.pk)
        with mock.patch.object(telegram, 'notify') as sent, translation.override('ru'):
            telegram.notify_refund(order, 'Payme')
        text = sent.call_args.args[0]
        self.assertIn('Payme: toʻlov qaytarildi', text)
        self.assertIn(order.order_no, text)
        self.assertIn('150000 soʻm', text)
        self.assertIn('panelda bekor qiling', text)
        self.assertEqual(sent.call_args.kwargs['event'], 'payment.refunded')
        data = sent.call_args.kwargs['data']['order']
        self.assertEqual((data['number'], data['total'], data['payment_method']),
                         (order.order_no, 150000, 'payme'))
        self.assertIn('/boshqaruv/', data['admin_url'])

    def test_a_cancel_before_performing_tells_nobody(self):
        self.create('A' * 24)
        with mock.patch('core.telegram.notify_refund') as told:
            self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 3})
        told.assert_not_called()

    def test_a_refund_asked_again_tells_once(self):
        self.create('A' * 24)
        self.call('PerformTransaction', {'id': 'A' * 24})
        with mock.patch('core.telegram.notify_refund') as told:
            first = self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 5})
            again = self.call('CancelTransaction', {'id': 'A' * 24, 'reason': 5})
        self.assertEqual(first, again)
        told.assert_called_once()
