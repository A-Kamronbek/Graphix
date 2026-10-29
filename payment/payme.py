"""Payme's Merchant API: the six calls Payme makes to the shop (§17 #421).

Payme asks before it charges (``CheckPerformTransaction``), opens a
transaction (``CreateTransaction``), and then completes it
(``PerformTransaction``) or cancels it (``CancelTransaction``);
``CheckTransaction`` reads one back and ``GetStatement`` lists them for a
reconciliation. Each is a JSON-RPC call posted to ``/payment/payme/update/``,
signed with HTTP Basic auth whose password is the cashbox key, and every
answer is HTTP 200, an error included. The rules are Payme's own, at
developer.help.paycom.uz ("Протокол Merchant API", "Методы Merchant API",
"Песочница").

tolov answered these calls until 2026-10-28, and broke the protocol where
Payme's sandbox looks: an unknown transaction was "wrong amount", a second
transaction for an order was "no such order", none ever timed out. Twice it
was unsafe: a cancelled transaction could still be performed, making its
order paid, and an order already paid could be paid for again. So the shop
answers them itself, here. The transactions stay in tolov's
``PaymentTransaction``, where the admin reads them, and
``apply_successful_payment`` stays the only place an order becomes paid
(§17 #253).

Payme's states are the model's numbers: 1 created, 2 performed, -1 cancelled
before it was performed, -2 cancelled after. No fiscal ``detail`` goes with
the answer: the shop is a sole trader with no IKPU code to put on a receipt,
and Payme's ``detail`` is optional (§17 #422).

Everything Payme can be told is in this module and is answered by
:func:`answer`. The view only hands it the body and the ``Authorization``
header.
"""
import base64
import binascii
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone as utc_zone
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from tolov.integrations.django.models import PaymentTransaction

from core import telegram
from . import services
from .models import Order

logger = logging.getLogger(__name__)

#: The field of Payme's ``account`` that names the order. The cashbox in
#: Payme Business is set up with the same name, and the pay link writes it
#: as ``ac.order_id``; its value is the order's id.
ACCOUNT_FIELD = 'order_id'

#: A transaction Payme created and has not performed in twelve hours is
#: cancelled, with reason 4 ("CreateTransaction": 43 200 000 ms from its
#: ``time``).
TIMEOUT_MS = 12 * 60 * 60 * 1000
REASON_TIMEOUT = 4

CREATED = PaymentTransaction.INITIATING                 # 1
PERFORMED = PaymentTransaction.SUCCESSFULLY             # 2
CANCELLED = PaymentTransaction.CANCELLED_DURING_INIT    # -1
CANCELLED_AFTER = PaymentTransaction.CANCELLED          # -2

#: Payme's error codes, each with the words Payme shows the payer. A code
#: from -31050 to -31099 is the merchant's own, for an ``account`` that is
#: wrong, and names the field it is about.
NOT_ALLOWED = (-32504, _('Ruxsat berilmagan.'))
UNREADABLE = (-32700, _('Soʻrovni oʻqib boʻlmadi.'))
MALFORMED = (-32600, _('Soʻrov notoʻgʻri tuzilgan.'))
NO_METHOD = (-32601, _('Bunday usul yoʻq.'))
SYSTEM = (-32400, _('Tizim xatosi.'))
WRONG_AMOUNT = (-31001, _('Summa buyurtma summasiga mos emas.'))
NO_TRANSACTION = (-31003, _('Tranzaksiya topilmadi.'))
CANNOT = (-31008, _('Bu amalni bajarib boʻlmaydi.'))
NO_ORDER = (-31050, _('Buyurtma topilmadi.'))
NOT_PAYABLE = (-31051, _('Bu buyurtma toʻlovni kutmayapti.'))


class Refusal(Exception):
    """What Payme is told instead of a result: a code, the words, a field."""

    def __init__(self, error, data=None):
        super().__init__(error[0])
        self.code, self.message = error
        self.data = data

    def as_error(self):
        """The ``error`` object, its message in each of Payme's three languages."""
        error = {'code': self.code, 'message': localised(self.message)}
        if self.data is not None:
            error['data'] = self.data
        return error


def localised(text):
    """``text`` in Russian, Uzbek and English, which Payme shows the payer."""
    words = {}
    for language in ('ru', 'uz', 'en'):
        with translation.override(language):
            words[language] = str(text)
    return words


def answer(body, authorization):
    """Payme's call, ``body`` as posted, answered as the JSON object to send back.

    The request's ``id`` comes back in the answer, so the JSON is read first,
    for it. Then the key, before anything else about the call is looked at: a
    caller without it learns no more than that.
    """
    request_id = None
    method = None
    try:
        try:
            call = json.loads(body)
        except (TypeError, ValueError):
            raise Refusal(UNREADABLE)
        if isinstance(call, dict):
            request_id = call.get('id')
        if not authorised(authorization):
            raise Refusal(NOT_ALLOWED)
        if (not isinstance(call, dict) or not isinstance(call.get('method'), str)
                or not isinstance(call.get('params'), dict)):
            raise Refusal(MALFORMED)
        method = call['method']
        handler = METHODS.get(method)
        if handler is None:
            raise Refusal(NO_METHOD, data=method)
        result = handler(call['params'])
    except Refusal as refusal:
        return {'jsonrpc': '2.0', 'id': request_id, 'error': refusal.as_error()}
    except Exception:
        # Payme asks again on a system error, so nothing is lost by saying so;
        # a 500 would be read the same way, with nothing in the log to say why.
        logger.exception('Payme %s failed', method or 'call')
        return {'jsonrpc': '2.0', 'id': request_id, 'error': Refusal(SYSTEM).as_error()}
    return {'jsonrpc': '2.0', 'id': request_id, 'result': result}


def authorised(header):
    """Whether the ``Authorization`` header carries the cashbox key.

    Payme signs as ``Paycom:<key>``. Only the key is compared, in constant
    time: it is the secret, and the only thing between a forged call and an
    order marked paid.
    """
    key = settings.PAYME_KEY
    if not key or not isinstance(header, str):
        return False
    scheme, _space, encoded = header.partition(' ')
    if scheme.lower() != 'basic':
        return False
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode('utf-8')
    except (binascii.Error, ValueError):
        return False
    _login, colon, password = decoded.partition(':')
    return bool(colon) and hmac.compare_digest(password.encode('utf-8'), key.encode('utf-8'))


# -------------------------------------------------------------------- reading

def _text(params, name):
    """A string parameter Payme must send, or the call is malformed."""
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise Refusal(MALFORMED)
    return value


def _whole(params, name):
    """A whole-number parameter Payme must send: a time, a reason."""
    value = params.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise Refusal(MALFORMED)
    return value


def _order(params, *, lock=False):
    """The order Payme's ``account`` names, if it may be paid for through Payme.

    Only an order placed with Payme and still awaiting payment: one already
    paid is not paid for twice, a cancelled one is not paid for at all
    (§17 #346), and an order placed with Click is Click's to take.
    """
    account = params.get('account')
    raw = account.get(ACCOUNT_FIELD) if isinstance(account, dict) else None
    if isinstance(raw, str) and raw.isdigit():
        raw = int(raw)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise Refusal(NO_ORDER, data=ACCOUNT_FIELD)
    rows = Order.objects.select_for_update() if lock else Order.objects
    order = rows.filter(pk=raw).first()
    if order is None:
        raise Refusal(NO_ORDER, data=ACCOUNT_FIELD)
    if (order.status != Order.Status.PAYING
            or order.payment_method != Order.PaymentMethod.PAYME):
        raise Refusal(NOT_PAYABLE, data=ACCOUNT_FIELD)
    return order


def _amount(order, params):
    """The amount in tiyin, which has to be the order's ``total_price`` × 100."""
    raw = params.get('amount')
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise Refusal(WRONG_AMOUNT)
    amount = Decimal(str(raw))
    if amount != Decimal(order.total_price) * 100:
        raise Refusal(WRONG_AMOUNT)
    return amount


def _ms(moment):
    """A moment as Payme writes one: milliseconds since 1970, or 0 for none."""
    return int(moment.timestamp() * 1000) if moment else 0


def _now_ms():
    return _ms(timezone.now())


def _created_at(tx):
    """When Payme created ``tx``, in its own milliseconds."""
    return (tx.extra_data or {}).get('time') or _ms(tx.created_at)


def _expired(tx):
    return _now_ms() - _created_at(tx) > TIMEOUT_MS


def _time_out(tx):
    """Cancel ``tx`` for having waited past Payme's twelve hours."""
    tx.state = CANCELLED
    tx.reason = REASON_TIMEOUT
    tx.cancelled_at = timezone.now()
    tx.save(update_fields=['state', 'reason', 'cancelled_at', 'updated_at'])


def _locked(payme_id):
    """Payme's transaction ``payme_id``, locked until the caller's block ends."""
    return (PaymentTransaction.objects.select_for_update()
            .filter(gateway=PaymentTransaction.PAYME, transaction_id=payme_id).first())


def _open_elsewhere(order, payme_id=None):
    """Whether another of Payme's transactions is open for ``order``.

    One that has outlived Payme's twelve hours is cancelled here, as Payme
    cancels it, and does not count.
    """
    rows = (PaymentTransaction.objects.select_for_update()
            .filter(gateway=PaymentTransaction.PAYME, account_id=str(order.pk), state=CREATED))
    if payme_id:
        rows = rows.exclude(transaction_id=payme_id)
    for tx in rows:
        if _expired(tx):
            _time_out(tx)
        else:
            return True
    return False


# -------------------------------------------------------------------- methods

def check_perform_transaction(params):
    """May this order be paid for, this amount? Asked before the card is charged.

    The order, then the amount, as Payme's sandbox asks them; then whether
    another transaction is already open for it.
    """
    with transaction.atomic():
        order = _order(params)
        _amount(order, params)
        if _open_elsewhere(order):
            raise Refusal(CANNOT)
    return {'allow': True}


def create_transaction(params):
    """Open Payme's transaction for an order, or answer again for one already open.

    Payme sends the same call again when it did not hear the answer, and
    hears the same answer. A transaction that is no longer open, or that
    waited past twelve hours, cannot be created again, and a second one for
    an order that already has one open is refused. The order's row is locked,
    so two calls for one order cannot both open one.
    """
    payme_id = _text(params, 'id')
    created = _whole(params, 'time')
    refusal = None
    with transaction.atomic():
        order = _order(params, lock=True)
        amount = _amount(order, params)
        tx = _locked(payme_id)
        if tx is not None:
            if tx.state != CREATED:
                refusal = CANNOT
            elif _expired(tx):
                _time_out(tx)
                refusal = CANNOT
        elif _now_ms() - created > TIMEOUT_MS or _open_elsewhere(order):
            refusal = CANNOT
        else:
            tx = PaymentTransaction.objects.create(
                gateway=PaymentTransaction.PAYME, transaction_id=payme_id,
                account_id=str(order.pk), amount=amount / 100, state=CREATED,
                extra_data={'time': created, 'account': params.get('account')})
    # Refused outside the block, so a transaction timed out above stays so.
    if refusal:
        raise Refusal(refusal)
    return {'create_time': _ms(tx.created_at), 'transaction': str(tx.pk), 'state': tx.state}


def perform_transaction(params):
    """Payme has the money: the transaction is performed and the order paid.

    Performed once; asked again, Payme hears the same answer. A cancelled
    transaction is never performed, and one that waited past twelve hours is
    cancelled instead. The order is made paid whatever it reads by now,
    because the money is real (§17 #346).
    """
    payme_id = _text(params, 'id')
    refusal = None
    with transaction.atomic():
        tx = _locked(payme_id)
        if tx is None:
            refusal = NO_TRANSACTION
        elif tx.state == CREATED and _expired(tx):
            _time_out(tx)
            refusal = CANNOT
        elif tx.state == CREATED:
            tx.state = PERFORMED
            tx.performed_at = timezone.now()
            tx.save(update_fields=['state', 'performed_at', 'updated_at'])
            order = Order.objects.filter(pk=tx.account_id).first()
            if order is None:
                logger.error('Payme performed %s for order %s, which is not there',
                             payme_id, tx.account_id)
            else:
                services.apply_successful_payment(order)
        elif tx.state != PERFORMED:
            refusal = CANNOT
    if refusal:
        raise Refusal(refusal)
    return {'transaction': str(tx.pk), 'perform_time': _ms(tx.performed_at), 'state': tx.state}


def cancel_transaction(params):
    """Payme cancels a transaction: before it was performed, or a refund after.

    Before: the order is left awaiting payment, so the customer can try
    again, and it is cancelled after three days if nobody does, as a failed
    Click payment is (§17 #373, #396). After: the money goes back to the
    customer, but the order stays a sale, because only staff can undo one
    and give back its stock; the shop is told, so somebody does (§17 #421).
    Cancelled already, it is answered as it stands.
    """
    payme_id = _text(params, 'id')
    reason = _whole(params, 'reason')
    refunded = None
    with transaction.atomic():
        tx = _locked(payme_id)
        if tx is None:
            raise Refusal(NO_TRANSACTION)
        if tx.state in (CREATED, PERFORMED):
            refunded = tx.state == PERFORMED
            tx.state = CANCELLED_AFTER if refunded else CANCELLED
            tx.reason = reason
            tx.cancelled_at = timezone.now()
            tx.save(update_fields=['state', 'reason', 'cancelled_at', 'updated_at'])
        if refunded:
            order = Order.objects.filter(pk=tx.account_id).first()
            if order is not None:
                # Queued, and sent once this commits.
                telegram.notify_refund(order, 'Payme')
    return {'transaction': str(tx.pk), 'cancel_time': _ms(tx.cancelled_at), 'state': tx.state}


def check_transaction(params):
    """A transaction as it stands."""
    tx = (PaymentTransaction.objects
          .filter(gateway=PaymentTransaction.PAYME, transaction_id=_text(params, 'id')).first())
    if tx is None:
        raise Refusal(NO_TRANSACTION)
    return {
        'create_time': _ms(tx.created_at),
        'perform_time': _ms(tx.performed_at),
        'cancel_time': _ms(tx.cancelled_at),
        'transaction': str(tx.pk),
        'state': tx.state,
        'reason': tx.reason,
    }


def get_statement(params):
    """Every transaction Payme created from ``from`` to ``to``, both included.

    By Payme's own creation time, in the order Payme created them. The rows
    are first narrowed by the shop's time, a day wider on each side, and then
    read exactly; the two clocks differ by the seconds a call takes.
    """
    start, end = _whole(params, 'from'), _whole(params, 'to')
    near = timedelta(days=1)
    rows = PaymentTransaction.objects.filter(
        gateway=PaymentTransaction.PAYME,
        created_at__gte=datetime.fromtimestamp(start / 1000, tz=utc_zone.utc) - near,
        created_at__lte=datetime.fromtimestamp(end / 1000, tz=utc_zone.utc) + near)
    found = sorted((tx for tx in rows if start <= _created_at(tx) <= end), key=_created_at)
    return {'transactions': [{
        'id': tx.transaction_id,
        'time': _created_at(tx),
        'amount': int(tx.amount * 100),
        'account': {ACCOUNT_FIELD: int(tx.account_id) if tx.account_id.isdigit() else tx.account_id},
        'create_time': _ms(tx.created_at),
        'perform_time': _ms(tx.performed_at),
        'cancel_time': _ms(tx.cancelled_at),
        'transaction': str(tx.pk),
        'state': tx.state,
        'reason': tx.reason,
        'receivers': None,
    } for tx in found]}


METHODS = {
    'CheckPerformTransaction': check_perform_transaction,
    'CreateTransaction': create_transaction,
    'PerformTransaction': perform_transaction,
    'CancelTransaction': cancel_transaction,
    'CheckTransaction': check_transaction,
    'GetStatement': get_statement,
}
