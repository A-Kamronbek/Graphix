"""Click is told "already paid" when it would charge a paid order again, and
"cancelled" when it reports that a payment failed.

tolov answers Click's Prepare for an order that is already paid with success,
so Click goes on to charge the card a second time; and it answers the Complete
of such a second charge with success too, so the money is kept and nothing in
the shop shows it. Click's code for both is -4. Its successful Complete also
lacked ``merchant_confirm_id``, which Click's protocol lists in that answer and
click-pkg sent (plan §17 #395).

A Complete that reports a failed payment made tolov write "Error code: ..."
into an integer column, raise, and answer -7. Click's protocol asks for the
transaction to be cancelled and -9 answered (plan §17 #396).
"""
import hashlib

from django.test import override_settings
from django.urls import reverse

from panel.services import set_status
from payment.models import Order
from tolov.integrations.django.models import PaymentTransaction

from .test_phase16 import CLICK, PromoCase
from .test_phase7 import make_staff


@override_settings(TOLOV=CLICK, CLICK_SERVICE_ID='111', CLICK_MERCHANT_ID='222')
class ClickAnswerTests(PromoCase):
    """What the shop answers Click, signed as Click signs it."""

    PRICE = 165000          # one shirt and the delivery fee, no code

    def click(self, order, action, charge='1', prepare_id='', secret='sir', error='0'):
        """Post one Click callback for ``order``, for Click's charge ``charge``."""
        params = {'click_trans_id': '900%s%d' % (charge, order.pk), 'service_id': '111',
                  'merchant_trans_id': str(order.pk), 'amount': str(self.PRICE),
                  'action': str(action), 'error': error, 'sign_time': '2026-10-19 12:00:00'}
        if prepare_id:
            params['merchant_prepare_id'] = str(prepare_id)
        signed = (params['click_trans_id'] + '111' + secret + params['merchant_trans_id']
                  + str(prepare_id) + params['amount'] + params['action'] + params['sign_time'])
        params['sign_string'] = hashlib.md5(signed.encode()).hexdigest()
        return self.client.post(reverse('click_webhook'), params).json()

    def pay(self, order, charge='1'):
        """One whole Click payment: Prepare, then Complete. Returns both answers."""
        prepared = self.click(order, 0, charge)
        done = self.click(order, 1, charge, prepare_id=prepared.get('merchant_prepare_id', ''))
        return prepared, done

    def successes(self, order):
        return PaymentTransaction.objects.filter(
            gateway=PaymentTransaction.CLICK, account_id=str(order.pk),
            state=PaymentTransaction.SUCCESSFULLY).count()

    def test_a_payment_is_answered_as_before_and_confirmed_by_id(self):
        order = self.order(None)
        prepared, done = self.pay(order)
        self.assertEqual(prepared['error'], 0, prepared)
        self.assertEqual(done['error'], 0, done)
        self.assertEqual(done['merchant_confirm_id'], prepared['merchant_prepare_id'])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_paid_order_is_refused_before_click_charges_again(self):
        order = self.order(None)
        self.pay(order)
        again = self.click(order, 0, charge='2')
        self.assertEqual(again['error'], -4, again)
        self.assertEqual(PaymentTransaction.objects.filter(
            gateway=PaymentTransaction.CLICK).count(), 1)

    def test_an_order_staff_marked_paid_is_refused_too(self):
        order = self.order(None)
        staff = make_staff()
        set_status(order, Order.Status.PAID, by=staff)
        self.assertEqual(self.click(order, 0)['error'], -4)
        set_status(Order.objects.get(pk=order.pk), Order.Status.DONE, by=staff)
        self.assertEqual(self.click(order, 0)['error'], -4)

    def test_a_second_charge_completed_on_a_paid_order_is_refused(self):
        """Two pay pages, both prepared while the order waited: the second is given back."""
        order = self.order(None)
        first = self.click(order, 0, charge='1')
        second = self.click(order, 0, charge='2')
        self.assertEqual((first['error'], second['error']), (0, 0))
        done = self.click(order, 1, charge='1', prepare_id=first['merchant_prepare_id'])
        self.assertEqual(done['error'], 0, done)
        late = self.click(order, 1, charge='2', prepare_id=second['merchant_prepare_id'])
        self.assertEqual(late['error'], -4, late)
        self.assertEqual(self.successes(order), 1)

    def test_click_repeating_a_complete_is_still_answered_success(self):
        order = self.order(None)
        prepared, done = self.pay(order)
        again = self.click(order, 1, prepare_id=prepared['merchant_prepare_id'])
        self.assertEqual(again['error'], 0, again)
        self.assertEqual(self.successes(order), 1)

    def test_an_unsigned_caller_learns_nothing_about_a_paid_order(self):
        order = self.order(None)
        self.pay(order)
        self.assertEqual(self.click(order, 0, charge='2', secret='wrong')['error'], -1)

    def test_an_order_that_is_not_there_is_still_click_s_minus_five(self):
        order = self.order(None)
        order.pk = 999999
        self.assertEqual(self.click(order, 0)['error'], -5)

    def test_a_cancelled_order_is_still_refused_as_not_there(self):
        """§17 #346 is unchanged: a cancelled order is -5, not -4."""
        from payment import services
        order = self.order(None)
        services.cancel_order(order)
        self.assertEqual(self.click(order, 0)['error'], -5)

    # ------------------------------------------------ a payment that failed at Click

    def charge(self, order, charge='1'):
        return PaymentTransaction.objects.get(gateway=PaymentTransaction.CLICK,
                                              transaction_id='900%s%d' % (charge, order.pk))

    def test_a_failed_payment_is_cancelled_and_answered_minus_nine(self):
        order = self.order(None)
        prepared = self.click(order, 0)
        failed = self.click(order, 1, prepare_id=prepared['merchant_prepare_id'], error='-5017')
        self.assertEqual(failed['error'], -9, failed)
        charge = self.charge(order)
        self.assertEqual(charge.state, PaymentTransaction.CANCELLED)
        self.assertEqual(charge.reason, -5017)
        # The order waits for payment as before, so the customer can try again.
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAYING)

    def test_the_customer_can_pay_after_a_failed_attempt(self):
        order = self.order(None)
        prepared = self.click(order, 0)
        self.click(order, 1, prepare_id=prepared['merchant_prepare_id'], error='-5017')
        _prepared, done = self.pay(order, charge='2')
        self.assertEqual(done['error'], 0, done)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_click_repeating_the_failure_is_answered_the_same(self):
        order = self.order(None)
        prepared = self.click(order, 0)
        for _ in range(2):
            failed = self.click(order, 1, prepare_id=prepared['merchant_prepare_id'],
                                error='-5017')
            self.assertEqual(failed['error'], -9, failed)

    def test_a_failure_reported_for_a_completed_charge_is_minus_four(self):
        order = self.order(None)
        prepared, _done = self.pay(order)
        late = self.click(order, 1, prepare_id=prepared['merchant_prepare_id'], error='-1')
        self.assertEqual(late['error'], -4, late)
        self.assertEqual(self.charge(order).state, PaymentTransaction.SUCCESSFULLY)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_a_failure_reported_for_a_charge_never_prepared_is_minus_six(self):
        order = self.order(None)
        self.assertEqual(self.click(order, 1, prepare_id='1', error='-5017')['error'], -6)
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_an_unsigned_failure_changes_nothing(self):
        order = self.order(None)
        prepared = self.click(order, 0)
        forged = self.click(order, 1, prepare_id=prepared['merchant_prepare_id'],
                            error='-5017', secret='wrong')
        self.assertEqual(forged['error'], -1)
        self.assertEqual(self.charge(order).state, PaymentTransaction.INITIATING)
