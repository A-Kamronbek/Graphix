"""Asking to return or exchange part of a delivered order (§17 #399).

Phase 23 part B. What a customer may ask about, checked here and nowhere else,
so the page, its tests and anything later that offers the same thing cannot
disagree about it: which orders, which lines and how many, what has to come
with the request, and how many requests a day.

A request is a message to the shop with structure, not an operation. Nothing
here moves stock or money; staff do that on the order itself, as they always
have, after reading the request.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from core import legal, telegram
from product import images
from user.models import normalize_uz_phone, phone_regex

from .models import Order, ReturnImage, ReturnLine, ReturnRequest

#: Photographs a request may carry, as a review may (§17 #132).
MAX_PHOTOS = 4

#: Characters in the explanation, as a review's text.
MAX_TEXT = 2000

#: Requests a customer may send in a day (§9 Phase 23 item 12). Counted from
#: the requests themselves rather than a cache counter: a counter kept a day
#: would outlive the hour the privacy policy promises for rate-limit data
#: (§17 #134), and the requests are already the record of what was sent.
DAILY = 5


class Refused(Exception):
    """A request that cannot be sent, with the sentence that says why."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def eligible_orders(user):
    """The customer's orders a request may be about: delivered, newest first.

    "Bajarildi" is the one status that means the parcel reached the customer;
    a cancelled order is never one of them (§9 Phase 23 item 7).
    """
    return (Order.objects.filter(user=user, status=Order.Status.DONE)
            .order_by('-created_at', '-id'))


def held_quantities(order):
    """How much of each of ``order``'s lines an open request already holds."""
    rows = (ReturnLine.objects
            .filter(request__order=order, request__status__in=ReturnRequest.OPEN)
            .values('item_id').annotate(n=Sum('quantity')))
    return {row['item_id']: row['n'] for row in rows}


def lines_of(order):
    """``order``'s lines, each with what may still be asked about it.

    A line in an open request is held by it: one open request per order line
    (item 12). ``free`` is how many of it may be asked about now, 0 for a
    held line; ``sizes`` are the sizes its product is made in, for an
    exchange.
    """
    held = held_quantities(order)
    items = list(order.cart.cart_items
                 .select_related('variant__product', 'variant__size')
                 .prefetch_related('variant__product__variants__size')
                 .order_by('id'))
    lines = []
    for item in items:
        product = item.variant.product
        sizes = sorted({v.size for v in product.variants.all() if v.size_id},
                       key=lambda size: (size.order, size.pk))
        lines.append({
            'item': item,
            'held': item.pk in held,
            'free': 0 if item.pk in held else item.quantity,
            'sizes': sizes,
        })
    return lines


def is_late(order, on=None):
    """Has the policy's period for a size or a change of mind passed?

    Counted from the day of purchase, as the owner's document says (§17
    #398), to ``on``: today for the form, the day it was sent for the panel.
    Past it a request is still sent; the form says the policy may not cover
    it, and the owner decides. A fault is not held to it (§17 #406).
    """
    on = on or timezone.localdate()
    return (on - timezone.localdate(order.created_at)).days > legal.EXCHANGE_DAYS


def sent_today(user):
    """How many requests the customer has sent in the last day."""
    since = timezone.now() - timedelta(days=1)
    return ReturnRequest.objects.filter(user=user, created_at__gte=since).count()


def clean(user, order, data, uploads):
    """Check a request as the form sent it, and return what to save.

    ``data`` is the POST; ``uploads`` the photographs. Raises :class:`Refused`
    with the first thing wrong, in the order a customer would fix them.
    Returns a dict for :func:`create`.
    """
    if sent_today(user) >= DAILY:
        raise Refused(_('Bir kunda koʻpi bilan %(n)d ta soʻrov yuborish mumkin. '
                        'Ertaga qayta urinib koʻring yoki bizga yozing.') % {'n': DAILY})
    if order.status != Order.Status.DONE:
        raise Refused(_('Bu buyurtma boʻyicha soʻrov yuborib boʻlmaydi.'))

    kind = data.get('kind', '')
    if kind not in ReturnRequest.Kind.values:
        raise Refused(_('Qaytarish yoki almashtirishni tanlang.'))

    chosen = []
    for line in lines_of(order):
        item = line['item']
        try:
            quantity = int(data.get('qty-%d' % item.pk) or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            continue
        if line['held']:
            raise Refused(_('«%(name)s» boʻyicha soʻrov allaqachon koʻrib chiqilmoqda.')
                          % {'name': item.variant.product.name})
        if quantity > line['free']:
            raise Refused(_('«%(name)s»: buyurtmada %(n)d dona bor.')
                          % {'name': item.variant.product.name, 'n': line['free']})
        size = None
        if kind == ReturnRequest.Kind.EXCHANGE:
            wanted = data.get('size-%d' % item.pk) or ''
            size = next((s for s in line['sizes'] if str(s.pk) == wanted), None)
            if size is None:
                raise Refused(_('«%(name)s»: almashtirish uchun oʻlchamni tanlang.')
                              % {'name': item.variant.product.name})
        chosen.append((item, quantity, size))
    if not chosen:
        raise Refused(_('Qaysi mahsulot va nechta ekanini tanlang.'))

    reason = data.get('reason', '')
    if reason not in ReturnRequest.Reason.values:
        raise Refused(_('Sababni tanlang.'))

    explanation = (data.get('explanation') or '').strip()
    if not explanation:
        raise Refused(_('Nima boʻlganini qisqacha yozing.'))
    if len(explanation) > MAX_TEXT:
        raise Refused(_('Tushuntirish %(n)d belgidan oshmasligi kerak.') % {'n': MAX_TEXT})

    phone = normalize_uz_phone((data.get('phone') or '').strip())
    try:
        phone_regex(phone)
    except ValidationError:
        raise Refused(_('Telefon raqamini +998 XX XXX XX XX koʻrinishida yozing.'))

    uploads = [upload for upload in uploads if upload]
    if len(uploads) > MAX_PHOTOS:
        raise Refused(_('Koʻpi bilan %(n)d ta rasm yuborish mumkin.') % {'n': MAX_PHOTOS})
    if reason in ReturnRequest.PHOTO_REASONS and not uploads:
        raise Refused(_('Bu sabab uchun mahsulot rasmini yuboring.'))
    try:
        photos = [images.sanitise(upload, name_hint='qaytarish') for upload in uploads]
    except ValidationError as exc:
        raise Refused(exc.messages[0])

    return {'kind': kind, 'reason': reason, 'explanation': explanation,
            'phone': phone, 'lines': chosen, 'photos': photos}


def create(user, order, cleaned):
    """Save a request :func:`clean` passed, and tell the shop once it is in."""
    with transaction.atomic():
        request = ReturnRequest.objects.create(
            user=user, order=order, kind=cleaned['kind'], reason=cleaned['reason'],
            explanation=cleaned['explanation'], phone=cleaned['phone'])
        for item, quantity, size in cleaned['lines']:
            ReturnLine.objects.create(request=request, item=item, quantity=quantity,
                                      size_wanted=size)
        for position, photo in enumerate(cleaned['photos']):
            ReturnImage.objects.create(request=request, picture=photo, order=position)
        # Composed at commit, as a review's is: the lines and the photographs
        # are written after the request, inside the same transaction.
        transaction.on_commit(lambda: telegram.notify_return(request))
    return request


def answer(request, *, status, text, by):
    """Staff's decision on a request: its status and the answer the customer reads.

    Closing it starts the year it is kept (§17 #406); opening it again stops
    that clock.
    """
    if status not in ReturnRequest.Status.values:
        raise Refused(_('Notoʻgʻri holat.'))
    text = (text or '').strip()
    if len(text) > MAX_TEXT:
        raise Refused(_('Javob %(n)d belgidan oshmasligi kerak.') % {'n': MAX_TEXT})
    now = timezone.now()
    changed = text != request.answer
    request.status = status
    request.answer = text
    if changed:
        request.answered_by, request.answered_at = by, now
    if status in ReturnRequest.CLOSED:
        request.closed_at = request.closed_at or now
    else:
        request.closed_at = None
    request.save(update_fields=['status', 'answer', 'answered_by', 'answered_at',
                                'closed_at'])
    return request
