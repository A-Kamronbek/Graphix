"""Suggesting one's own design to the shop (§17 #402).

Phase 23 part E. What a customer may send, checked here and nowhere else, so
the page, its tests and the panel cannot disagree about it: the fields, the
print's colours, the pictures, and how many suggestions a day.

A suggestion is a message to the owner with structure, not an order. Nothing
is priced or paid on the site; the owner rings or writes back.
"""
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from product import images
from product.models import Size
from user.models import normalize_uz_phone, phone_regex

from . import telegram
from .models import DesignImage, DesignRequest

#: Pictures a suggestion may carry: a sketch, a logo, an example (item 25).
MAX_PHOTOS = 4

#: Characters in the idea, as a review's text and a return's explanation.
MAX_TEXT = 2000

#: The print's colours, picked with the browser's colour picker (item 25).
MAX_COLOURS = 3

#: Garments a customer may ask for at once. A bigger run is a conversation
#: with the owner, which the suggestion starts anyway.
MAX_QUANTITY = 100

#: Suggestions a customer may send in a day (item 27). Counted from the
#: suggestions themselves, as returns are (`payment.returns.DAILY`): a cache
#: counter kept a day would outlive the hour the privacy policy promises for
#: rate-limit data (§17 #134).
DAILY = 5

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


class Refused(Exception):
    """A suggestion that cannot be sent, with the sentence that says why."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def sizes():
    """The sizes a suggestion may name: the shop's own, in their order."""
    return Size.objects.order_by('order', 'pk')


def colour_slots(data=None):
    """The three colour rows of the form, each ``(n, chosen, value)``.

    ``data`` is a refused POST, so the rows come back as they were sent; on a
    fresh page every row is off and black, the colour picker's own start.
    """
    data = data or {}
    rows = []
    for n in range(1, MAX_COLOURS + 1):
        value = data.get('colour-%d' % n) or ''
        rows.append((n, bool(data.get('use-colour-%d' % n)),
                     value.lower() if _HEX.match(value) else '#000000'))
    return rows


def sent_today(user):
    """How many suggestions the customer has sent in the last day."""
    since = timezone.now() - timedelta(days=1)
    return DesignRequest.objects.filter(user=user, created_at__gte=since).count()


def clean(user, data, uploads):
    """Check a suggestion as the form sent it, and return what to save.

    ``data`` is the POST; ``uploads`` the pictures. Raises :class:`Refused`
    with the first thing wrong, in the order the form asks for them. Returns
    a dict for :func:`create`.
    """
    if sent_today(user) >= DAILY:
        raise Refused(_('Bir kunda koʻpi bilan %(n)d ta taklif yuborish mumkin. '
                        'Ertaga qayta urinib koʻring yoki bizga yozing.') % {'n': DAILY})

    idea = (data.get('idea') or '').strip()
    if not idea:
        raise Refused(_('Gʻoyangizni qisqacha yozing.'))
    if len(idea) > MAX_TEXT:
        raise Refused(_('Gʻoya %(n)d belgidan oshmasligi kerak.') % {'n': MAX_TEXT})

    print_text = (data.get('print_text') or '').strip()
    text_max = DesignRequest._meta.get_field('print_text').max_length
    if len(print_text) > text_max:
        raise Refused(_('Bosiladigan matn %(n)d belgidan oshmasligi kerak.') % {'n': text_max})

    garment = data.get('garment', '')
    if garment not in DesignRequest.Garment.values:
        raise Refused(_('Futbolka yoki longslivni tanlang.'))

    colour = data.get('colour', '')
    if colour not in DesignRequest.Colour.values:
        raise Refused(_('Kiyim rangini tanlang.'))
    colour_other = ''
    if colour == DesignRequest.Colour.OTHER:
        colour_other = (data.get('colour_other') or '').strip()
        other_max = DesignRequest._meta.get_field('colour_other').max_length
        if not colour_other:
            raise Refused(_('Qaysi rang kerakligini yozing.'))
        if len(colour_other) > other_max:
            raise Refused(_('Rang nomi %(n)d belgidan oshmasligi kerak.') % {'n': other_max})

    # A colour input always holds a colour, so a row counts only when its box
    # is ticked; the page's script ticks it as soon as a colour is picked.
    colours = []
    for n, chosen, _value in colour_slots():
        value = data.get('colour-%d' % n) or ''
        if data.get('use-colour-%d' % n):
            if not _HEX.match(value):
                raise Refused(_('Bosma rangini qayta tanlang.'))
            if value.lower() not in colours:
                colours.append(value.lower())

    placement = data.get('placement', '')
    if placement not in DesignRequest.Placement.values:
        raise Refused(_('Dizayn qayerga tushirilishini tanlang.'))

    size = next((s for s in sizes() if str(s.pk) == (data.get('size') or '')), None)
    if size is None:
        raise Refused(_('Oʻlchamni tanlang.'))

    try:
        quantity = int(data.get('quantity') or 0)
    except (TypeError, ValueError):
        quantity = 0
    if not 1 <= quantity <= MAX_QUANTITY:
        raise Refused(_('Nechta kerakligini 1 dan %(n)d gacha yozing.') % {'n': MAX_QUANTITY})

    phone = normalize_uz_phone((data.get('phone') or '').strip())
    try:
        phone_regex(phone)
    except ValidationError:
        raise Refused(_('Telefon raqamini +998 XX XXX XX XX koʻrinishida yozing.'))

    uploads = [upload for upload in uploads if upload]
    if len(uploads) > MAX_PHOTOS:
        raise Refused(_('Koʻpi bilan %(n)d ta rasm yuborish mumkin.') % {'n': MAX_PHOTOS})
    try:
        # Grey under a transparent picture, not the white a photograph gets:
        # a logo is often white on nothing, and on white it would vanish.
        photos = [images.sanitise(upload, name_hint='dizayn', background=images.GREY)
                  for upload in uploads]
    except ValidationError as exc:
        raise Refused(exc.messages[0])

    return {'idea': idea, 'print_text': print_text, 'garment': garment,
            'colour': colour, 'colour_other': colour_other,
            'print_colours': ' '.join(colours), 'placement': placement,
            'size': size.size, 'quantity': quantity, 'phone': phone,
            'photos': photos}


def create(user, cleaned):
    """Save a suggestion :func:`clean` passed, and tell the shop once it is in."""
    photos = cleaned.pop('photos')
    with transaction.atomic():
        request = DesignRequest.objects.create(user=user, **cleaned)
        for position, photo in enumerate(photos):
            DesignImage.objects.create(request=request, picture=photo, order=position)
        # Composed at commit, as a return's is: the pictures are written after
        # the suggestion, inside the same transaction.
        transaction.on_commit(lambda: telegram.notify_design(request))
    return request
