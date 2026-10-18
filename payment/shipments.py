"""An order's Uzpost shipment: made, cancelled and followed (§9 Phase 22).

The one place that turns an order into a shipment and a shipment's status
into the order's. ``core.uzpost`` knows Uzpost's addresses and answers; this
module knows the shop: which service a delivery method is, what is written on
the label, which of Uzpost's statuses moves an order, and when the customer is
sent an SMS.

Three callers. The panel's "Joʻnatma yaratish" calls :func:`create`, which is
staff accepting a paid order (§17 #379). A staff cancellation calls
:func:`cancel_for_order` once the order is cancelled (§17 #380). The
``uzpost_sync`` job calls :func:`follow` for each live shipment every 30
minutes. Nothing a customer does calls Uzpost: pages read the database.

What follows Uzpost only moves an order forward, never cancels one, never
touches one awaiting payment, and goes through ``panel.services.set_status``
with Uzpost named in the trail (§12 risk #35). A status the code does not
know changes nothing and tells the owner once.
"""
import logging
import time
from collections import namedtuple
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy

from core import legal, sms, telegram, uzpost
from panel.models import UZPOST_NOTE
from .models import SOLD, Order, Shipment, ShipmentStatus

logger = logging.getLogger(__name__)

#: Uzpost's statuses, as the shop says them. Seen on real shipments; nothing
#: lists them. A status missing here is shown as Uzpost wrote it.
STATUS_LABELS = {
    'requested': gettext_lazy('Soʻrov yuborilgan'),
    'unassigned': gettext_lazy('Rasmiylashtirildi'),
    'in_sorting_facility': gettext_lazy('Saralash markazida'),
    'in_transit': gettext_lazy('Yoʻlda'),
    'dispatched': gettext_lazy('Joʻnatildi'),
    'out_for_delivery': gettext_lazy('Yetkazib berishga chiqarildi'),
    'completed': gettext_lazy('Topshirildi'),
    'cancelled': gettext_lazy('Bekor qilindi'),
}

#: Made and not yet handed over: the order stays as it is.
WAITING = frozenset({'unassigned'})
#: On its way: the order reads "Yetkazilmoqda".
MOVING = frozenset({'in_sorting_facility', 'in_transit', 'dispatched', 'out_for_delivery'})
#: Delivered: the order reads "Bajarildi", which opens the review form.
DELIVERED = frozenset({'completed'})
CANCELLED = 'cancelled'

#: The shop's own word for a shipment asked for and not yet answered. Written
#: before Uzpost is asked, so that a request whose answer never arrives, or a
#: worker killed mid-request, leaves a mark that stops a second press from
#: making a second shipment. Never one of Uzpost's statuses.
REQUESTED = 'requested'

#: Seconds into a press after which the shipment is not asked for: the
#: request has 60 in all, and the create call needs room to answer.
DEADLINE = 15

#: Days after which a shipment that has not been delivered is no longer read:
#: one stuck in a status the shop does not act on is the owner's to follow.
FOLLOW_DAYS = 45

#: The forward order of the statuses the job may move between.
_RANK = {Order.Status.PAID: 1, Order.Status.PROCESSING: 2,
         Order.Status.ON_THE_WAY: 3, Order.Status.DONE: 4}

#: Sends of the arrival SMS that may fail before it is given up.
SMS_TRIES = 3


class ShipmentError(Exception):
    """Something staff are to be told, in words, when a shipment is not made."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


#: What cancelling an order did to its shipment: whether Uzpost cancelled it,
#: and the sentence for staff.
Cancelled = namedtuple('Cancelled', 'ok message')


def status_label(status):
    """Uzpost's status in the reader's language, or as Uzpost wrote it."""
    return STATUS_LABELS.get(status) or status


def arrived_statuses():
    """The statuses that mean an office order's parcel waits at the office."""
    return frozenset(settings.UZPOST_ARRIVAL_STATUSES)


def known_statuses():
    """Every status that has a meaning here; any other is reported."""
    return WAITING | MOVING | DELIVERED | arrived_statuses() | {CANCELLED}


def live_shipment(order):
    """The order's shipment that is not cancelled, or None. It may be a request."""
    return order.shipments.filter(cancelled_at__isnull=True).first()


def service_for(order):
    """The Uzpost service for the order's delivery method, or None."""
    if not order.delivery_option_id:
        return None
    return settings.UZPOST_SERVICES.get(order.delivery_option.code)


def item_count(order):
    """How many items the order holds, every size and quantity counted."""
    return sum(order.cart.cart_items.values_list('quantity', flat=True))


def weight_for(order):
    """What the parcel weighs on Uzpost's scales: a fixed weight an item."""
    each = Decimal(str(settings.UZPOST_ITEM_KG))
    return (each * max(item_count(order), 1)).quantize(Decimal('0.001'))


def can_create(order):
    """Whether the panel offers "Joʻnatma yaratish" on this order."""
    return (order.status in (Order.Status.PAID, Order.Status.PROCESSING)
            and service_for(order) is not None
            and live_shipment(order) is None
            and not _typed_office(order))


def _typed_office(order):
    """An office order placed before Phase 22, with the branch's index typed.

    Uzpost would send it to the district's Bir Qadam office, not the branch
    the customer chose and was shown, so it is made by hand in the cabinet.
    """
    return bool(order.delivery_option_id and order.delivery_option.requires_branch
                and order.postal_index)


def _phone(number):
    """A phone number as Uzpost takes it: + and the digits."""
    return '+' + ''.join(ch for ch in str(number) if ch.isdigit())


def payload(order, transportation):
    """What Uzpost is asked to carry, from whom and to whom.

    The sender is the shop, from its own district. The recipient is the name
    and number on the order. An office order is addressed by its district,
    with the district's name as the address line, since the customer typed no
    street (§17 #377). A home order is addressed by the street and either the
    district or, when the address came from the map, the pin. Every text goes
    through ``uzpost.plain``: Uzpost does not keep U+02BB (§17 #384).
    """
    service = service_for(order)
    # The address without its postal index, which Uzpost works out itself.
    street = legal.SELLER['address'].split(', ', 1)[-1]
    sender = {
        'customer': {'name': uzpost.plain(legal.SELLER['brand'])},
        'phone': _phone(legal.SELLER['phone']),
        'address': uzpost.plain(street),
        'jurisdiction': {'id': settings.UZPOST_SENDER_JURISDICTION},
    }
    name = order.recipient_name or order.user.get_full_name() or order.phone
    recipient = {'customer': {'name': uzpost.plain(name)}, 'phone': _phone(order.phone)}
    if order.delivery_option.requires_branch:
        recipient['address'] = uzpost.plain(order.district.name)
        recipient['jurisdiction'] = {'id': order.district.uzpost_id}
    elif (order.address_source == 'map' and order.latitude is not None
          and order.longitude is not None):
        recipient['address'] = uzpost.plain(order.address)
        recipient['lat'] = float(order.latitude)
        recipient['lon'] = float(order.longitude)
    else:
        recipient['address'] = uzpost.plain(order.address)
        recipient['jurisdiction'] = {'id': order.district.uzpost_id}
    return {
        'payment_type': 'credit_balance',
        'transportation_type': transportation,
        'service_type': {'code': service['code']},
        'sender_data': sender,
        'recipient_data': recipient,
        'dimensions': {'weight': float(weight_for(order))},
    }


def _refuse(order):
    """The reason this order gets no shipment now, or None. Read on a locked row."""
    if order.status not in (Order.Status.PAID, Order.Status.PROCESSING):
        return _("Joʻnatma faqat toʻlangan yoki jarayondagi buyurtmaga yaratiladi.")
    if live_shipment(order) is not None:
        return _("Bu buyurtmaning joʻnatmasi allaqachon bor.")
    if service_for(order) is None:
        return _("Bu yetkazib berish usuli uchun Uzpost xizmati belgilanmagan.")
    if not order.district_id or not order.district.uzpost_id or _typed_office(order):
        return _("Buyurtmaning tumani Uzpost roʻyxatida yoʻq. Joʻnatmani "
                 "my.pochta.uz kabinetida yarating.")
    return None


def create(order, by=None):
    """Make the order's shipment at Uzpost and record it. Returns the Shipment.

    Staff pressing the button is staff accepting the order, so a paid order
    moves to "Jarayonda" with it. Raises :class:`ShipmentError` with the
    sentence for staff.

    In three steps, so that no answer that goes missing can make a second
    shipment. First a request is written and committed, the order's row
    locked while it is: a second press finds it and is refused, whatever
    happens after. Then Uzpost is asked, with no lock held: the route's
    transportation type, then the shipment. A refusal from either withdraws
    the request; an answer that never comes leaves it, and staff are told to
    look in the cabinet before withdrawing it themselves. Last, the answer is
    written onto the request.
    """
    from panel.services import set_status

    if not uzpost.configured():
        raise ShipmentError(_("Uzpost sozlanmagan: serverdagi .env faylida "
                              "UZPOST_LOGIN va UZPOST_PASSWORD yoʻq."))
    started = time.monotonic()
    try:
        with transaction.atomic():
            locked = (Order.objects.select_for_update(of=('self',))
                      .select_related('delivery_option', 'district', 'user')
                      .get(pk=order.pk))
            refusal = _refuse(locked)
            if refusal:
                raise ShipmentError(refusal)
            service = service_for(locked)
            request = Shipment.objects.create(
                order=locked, service=service['code'], weight=weight_for(locked),
                status=REQUESTED, created_by=by if (by is not None and by.is_authenticated) else None)
    except IntegrityError:
        # Another press got its request in first.
        raise ShipmentError(_("Bu buyurtmaning joʻnatmasi allaqachon bor."))

    def withdraw(message):
        Shipment.objects.filter(pk=request.pk, uzpost_id__isnull=True).delete()
        raise ShipmentError(message)

    route = uzpost.transportation_type(service['id'], locked.district.uzpost_id)
    if not route.ok:
        withdraw(_("Uzpost bu yoʻnalish narxini bermadi: %(error)s") % {'error': route.error})
    if time.monotonic() - started > DEADLINE:
        withdraw(_("Uzpost sekin javob bermoqda. Birozdan keyin qayta urinib koʻring."))
    answer = uzpost.create_order(payload(locked, route.data))
    if not answer.ok:
        if answer.unknown:
            raise ShipmentError(_("Uzpost javob bermadi. Joʻnatma yaratilgan boʻlishi "
                                  "mumkin: qayta bosishdan oldin my.pochta.uz "
                                  "kabinetini tekshiring."))
        withdraw(_("Uzpost joʻnatmani qabul qilmadi: %(error)s") % {'error': answer.error})

    facts = answer.data
    now = timezone.now()
    # In the log before the row, so a shipment Uzpost made can always be
    # found again, whatever happens to the write below.
    logger.info("Uzpost shipment %s (id %s) created for %s",
                facts['number'], facts['id'], locked.order_no)
    with transaction.atomic():
        Shipment.objects.filter(pk=request.pk).update(
            uzpost_id=facts['id'], number=facts['number'], transportation=route.data,
            office_index=facts['office_index'], office_name=facts['office_name'],
            status=facts['status'], status_at=facts['status_at'] or now, read_at=now)
        shipment = Shipment.objects.get(pk=request.pk)
        ShipmentStatus.objects.create(shipment=shipment, status=shipment.status,
                                      at=shipment.status_at)
        current = Order.objects.select_for_update().get(pk=locked.pk)
        if current.status == Order.Status.PAID:
            set_status(current, Order.Status.PROCESSING, by=by)
    return shipment


def withdraw_request(order):
    """Drop a request Uzpost never answered, once staff have looked in the cabinet.

    Only a request with no Uzpost id: a shipment Uzpost made is cancelled at
    Uzpost, never forgotten here. Returns whether one was dropped.
    """
    return bool(Shipment.objects.filter(order=order, cancelled_at__isnull=True,
                                        uzpost_id__isnull=True)
                .update(cancelled_at=timezone.now()))


def label_url(shipment):
    """A fresh link to the shipment's label. Raises :class:`ShipmentError`."""
    if not shipment.uzpost_id:
        raise ShipmentError(_("Bu buyurtmaning joʻnatmasi yoʻq."))
    answer = uzpost.label(shipment.uzpost_id)
    if not answer.ok:
        raise ShipmentError(_("Uzpost yorliqni bermadi: %(error)s") % {'error': answer.error})
    return answer.data


def cancel_for_order(order):
    """Ask Uzpost to cancel a cancelled order's shipment. Returns Cancelled or None.

    None when there is no live shipment. Uzpost cancels a shipment only while
    it is new; once the parcel is with Uzpost it refuses, and staff are told
    so. The order stays cancelled either way (§17 #380). A request Uzpost
    never answered cannot be cancelled by number: staff are sent to the
    cabinet, and it stays until they withdraw it.
    """
    shipment = live_shipment(order)
    if shipment is None:
        return None
    if not shipment.uzpost_id:
        return Cancelled(False, _("Buyurtma bekor qilindi. Uzpost joʻnatma soʻroviga javob "
                                  "bermagan edi: my.pochta.uz kabinetini tekshiring."))
    answer = uzpost.cancel(shipment.number)
    if answer.ok:
        now = timezone.now()
        with transaction.atomic():
            done = (Shipment.objects.filter(pk=shipment.pk, cancelled_at__isnull=True)
                    .update(cancelled_at=now, status=CANCELLED, status_at=now,
                            read_at=now, reported_status=CANCELLED))
            if done:
                ShipmentStatus.objects.create(shipment=shipment, status=CANCELLED, at=now)
        return Cancelled(True, _("Uzpost joʻnatmasi %(number)s bekor qilindi.")
                         % {'number': shipment.number})
    if answer.unknown:
        return Cancelled(False, _("Buyurtma bekor qilindi, lekin Uzpost javob bermadi: "
                                  "%(number)s joʻnatmasi bekor boʻlganini my.pochta.uz "
                                  "kabinetida tekshiring.") % {'number': shipment.number})
    return Cancelled(False, _("Buyurtma bekor qilindi, lekin Uzpost %(number)s joʻnatmasini "
                              "bekor qilmadi: posilka allaqachon Uzpostda (%(error)s).")
                     % {'number': shipment.number, 'error': answer.error})


# ------------------------------------------------------------------ following

def to_follow():
    """The shipments the job reads: made at Uzpost, live, not delivered, not old."""
    since = timezone.now() - timedelta(days=FOLLOW_DAYS)
    return (Shipment.objects.filter(cancelled_at__isnull=True, uzpost_id__isnull=False,
                                    created_at__gte=since)
            .exclude(status__in=DELIVERED))


def _move_order(shipment):
    """Move the shipment's order forward to what its status says. Inside a transaction."""
    from panel.services import set_status

    status = shipment.status
    if status in DELIVERED:
        target = Order.Status.DONE
    elif status in MOVING or status in arrived_statuses():
        target = Order.Status.ON_THE_WAY
    else:
        return
    order = Order.objects.select_for_update().get(pk=shipment.order_id)
    # Forward only, and only an order the shop was paid for: never one
    # awaiting payment, never a cancelled one, never back from what staff set.
    if order.status not in _RANK or _RANK[target] <= _RANK[order.status]:
        return
    set_status(order, target, note=UZPOST_NOTE + status)


def _report(shipment):
    """Tell the owner once about a status that is cancelled or not known."""
    if shipment.status in known_statuses() - {CANCELLED}:
        return
    if not shipment.status or shipment.status == shipment.reported_status:
        return
    telegram.notify_shipment_status(shipment)
    shipment.reported_status = shipment.status


def follow(shipment):
    """Read one live shipment's status from Uzpost and act on a change.

    Returns True when Uzpost answered. A new status is recorded with its time,
    and the order moves forward if it says so; a status Uzpost cancelled
    or one the code does not know is reported to the owner once, and a
    cancelled shipment stops being live. Then the arrival SMS, if it is due.
    """
    if not shipment.uzpost_id:
        return False
    answer = uzpost.details(shipment.uzpost_id)
    now = timezone.now()
    if not answer.ok:
        return False
    facts = answer.data
    with transaction.atomic():
        current = Shipment.objects.select_for_update().get(pk=shipment.pk)
        if current.cancelled_at is not None:
            return True
        current.read_at = now
        changed = bool(facts['status']) and facts['status'] != current.status
        if changed:
            current.status = facts['status']
            current.status_at = facts['status_at'] or now
            ShipmentStatus.objects.create(shipment=current, status=current.status,
                                          at=current.status_at)
        # Uzpost may name the office later than it made the shipment.
        if facts['office_index']:
            current.office_index = facts['office_index']
        if facts['office_name']:
            current.office_name = facts['office_name']
        if current.status == CANCELLED:
            current.cancelled_at = now
        _report(current)
        # Only these: the arrival SMS's fields are claimed elsewhere, and a
        # whole-row save could write an old copy over them.
        current.save(update_fields=['read_at', 'status', 'status_at', 'office_index',
                                    'office_name', 'cancelled_at', 'reported_status'])
        # Only on a change: an order staff moved by hand stays where they put
        # it until Uzpost has something new to say.
        if changed:
            _move_order(current)
    send_arrival_sms(current)
    return True


def arrival_text(shipment):
    """The SMS that an office order's parcel is waiting at the office.

    Uzbek only, with a plain apostrophe, one SMS (§17 #292). Eskiz sends only
    a text it has approved (§17 #104).
    """
    index = f" (indeks {shipment.office_index})" if shipment.office_index else ''
    return (f"GRAPHIX: {shipment.order.order_no} buyurtmangiz pochta bo'limiga yetib "
            f"keldi{index}. Pasport bilan olib keting.")


def send_arrival_sms(shipment):
    """Send the arrival SMS once, if the shipment is an office order's and waits there.

    Only for an order still a sale: a parcel Uzpost would not call back from
    an order staff cancelled is not one to send the customer for. Marked sent
    in the same step that claims it, so two runs cannot both send it. A
    failed send is given back and tried again on a later run, up to
    :data:`SMS_TRIES` times. Returns True when it was sent now.
    """
    arrived = arrived_statuses()
    if not arrived or shipment.status not in arrived or shipment.cancelled_at is not None:
        return False
    order = Order.objects.select_related('delivery_option').get(pk=shipment.order_id)
    if not order.delivery_option_id or not order.delivery_option.requires_branch:
        return False
    if order.status not in SOLD:
        return False
    now = timezone.now()
    claimed = (Shipment.objects
               .filter(pk=shipment.pk, arrival_sms_at__isnull=True,
                       arrival_sms_tries__lt=SMS_TRIES)
               .update(arrival_sms_at=now))
    if not claimed:
        return False
    if sms.send_sms(order.phone, arrival_text(shipment)):
        shipment.arrival_sms_at = now
        return True
    Shipment.objects.filter(pk=shipment.pk).update(
        arrival_sms_at=None, arrival_sms_tries=F('arrival_sms_tries') + 1)
    logger.warning("Arrival SMS for %s not sent; will try again", order.order_no)
    return False
