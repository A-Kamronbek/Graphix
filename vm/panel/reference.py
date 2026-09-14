"""Editing the small reference tables from the panel.

Regions, districts, delivery tiers, tags, tag kinds, print methods, categories
and size charts are rows somebody changes two or three times a year: a district
gets renamed, a delivery price moves, a new collection tag appears. The screens
exist so that none of those needs a deploy (§9 Phase 7 items 5–8).

Every one of them is "a list of rows, a few fields editable in place", so
rather than eight bespoke endpoints there is one — and the thing that makes one
endpoint safe is the table below. A field that is not named there cannot be
written, whatever arrives in the POST. Without it, an endpoint that takes a
model, a field and a value is a way to set *anything* on *any* row, which is a
hole large enough to change a price to zero through.

Deleting is a second, shorter allowlist. Regions, districts and delivery tiers
are missing from it deliberately: an order points at all three, and the history
of where a parcel went is not something a tidy-up should be able to remove.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.utils.translation import gettext as _

from payment.models import DeliveryOption, District, Region
from product.models import (Category, PrintMethod, SizeChart, Tag, TagKind)

#: What each screen is allowed to change, and how to read the value. Nothing
#: else on any of these models is reachable from the panel.
EDITABLE = {
    'region': (Region, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
        'postal_prefix': 'prefix', 'is_active': 'bool',
    }),
    'district': (District, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
        'is_active': 'bool',
    }),
    'delivery': (DeliveryOption, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
        'note': 'text', 'note_ru': 'text', 'note_en': 'text',
        'price': 'money', 'free_from_items': 'count', 'is_active': 'bool',
    }),
    'tag': (Tag, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
        'kind': 'tagkind',
    }),
    'tagkind': (TagKind, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
    }),
    'method': (PrintMethod, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
    }),
    'category': (Category, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
    }),
    # A name and a picture is the whole of a chart (§17 #172). The picture is
    # not here because it is a file: it is set when the chart is created and
    # replaced by creating another, which is one upload path rather than two.
    'chart': (SizeChart, {
        'name': 'text', 'note': 'text', 'note_ru': 'text', 'note_en': 'text',
    }),
}

#: What may be removed, and what it costs. Everything here is either unlinked
#: on delete (a tag comes off its products, a chart and a category fall back to
#: null) or protected by the database (a kind or a method that is in use).
#: Anything an order points at is absent on purpose.
DELETABLE = {'tag', 'tagkind', 'method', 'category', 'chart'}


def _money(raw):
    """Read a price out of a text box: spaces stripped, comma as a decimal point.

    Rounds half **up**, not to even. Python's default rounds 2500.5 down to
    2500 and 2501.5 up to 2502, which is correct for statistics and wrong for
    money — §17 already settled this once, for a product rating.
    """
    try:
        value = Decimal(str(raw).strip().replace(' ', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise ValidationError(_('Notoʻgʻri narx.'))
    if value < 0:
        raise ValidationError(_('Narx manfiy boʻlishi mumkin emas.'))
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _prefix(raw):
    """A postal prefix is two or three digits, or nothing at all.

    Nothing at all is the escape row, and it is meaningful: a region with no
    prefix accepts any index, because we do not know where an address we could
    not classify sits and the only honest answer is not to guess (§17 #86).
    """
    value = str(raw).strip()
    if value and not (value.isdigit() and 2 <= len(value) <= 3):
        raise ValidationError(_('Indeks prefiksi 2 yoki 3 ta raqam boʻlishi kerak.'))
    return value


def _tagkind(raw):
    """The axis a tag sits on, by id, or nothing.

    A tag with no kind is a real state — it is the one a tag is in a second
    after somebody types its name — so a blank clears the field rather than
    being refused.
    """
    value = str(raw).strip()
    if not value.isdigit():
        return None
    kind = TagKind.objects.filter(pk=value).first()
    if kind is None:
        raise ValidationError(_('Bunday teg turi yoʻq.'))
    return kind


def _count(raw):
    """A whole number of items, never negative. Blank counts as zero."""
    try:
        return max(0, int(str(raw).strip() or 0))
    except (TypeError, ValueError):
        raise ValidationError(_('Notoʻgʻri son.'))


READERS = {
    'text': lambda raw: str(raw).strip(),
    'bool': lambda raw: str(raw) in ('1', 'true', 'on'),
    'money': _money,
    'prefix': _prefix,
    'count': _count,
    'tagkind': _tagkind,
}


def set_field(kind, pk, field, raw):
    """Write one field on one reference row. Returns the stored value.

    Raises :class:`~django.core.exceptions.ValidationError` for anything the
    table above does not allow, which includes a field that exists on the model
    but is not meant to be edited here — ``Region.code`` is the SOATO code and
    changing it would quietly detach the row from the classifier it came from.
    """
    if kind not in EDITABLE:
        raise ValidationError(_('Notoʻgʻri jadval.'))
    model, fields = EDITABLE[kind]
    if field not in fields:
        raise ValidationError(_('Notoʻgʻri maydon.'))

    row = model.objects.filter(pk=pk).first()
    if row is None:
        raise ValidationError(_('Topilmadi.'))

    value = READERS[fields[field]](raw)

    # The Uzbek name is the source every other language falls back to, and it
    # is what the site renders — a size chart whose name was cleared put an
    # empty <h2> on the public size-guide page. Russian and English may be
    # blank; this one may not.
    if field == 'name' and not value:
        raise ValidationError(_('Nomi boʻsh boʻlishi mumkin emas.'))

    # A name longer than its column is a validation problem, and it was being
    # answered with a 500: the value went straight to Postgres, which refuses
    # it, and the screen showed "could not save" while the log filled up with
    # tracebacks. A paste is all it takes — none of these boxes is longer than
    # 255 characters and none of them said so.
    limit = getattr(model._meta.get_field(field), 'max_length', None)
    if limit and isinstance(value, str) and len(value) > limit:
        raise ValidationError(
            _('Juda uzun — koʻpi bilan %(n)d ta belgi.') % {'n': limit})

    setattr(row, field, value)
    row.save(update_fields=[field])
    # A foreign key answers with its own name, because that is what the screen
    # has to show once the select has been changed.
    return getattr(value, 'name', value)


def delete_row(kind, pk):
    """Remove one reference row. Returns what it was called.

    Refuses what the database refuses: a tag kind with tags on it and a print
    method a product is marked with are both ``PROTECT``, and the honest answer
    is "something is using this", not a cascade that quietly unfiles them.
    """
    if kind not in DELETABLE:
        raise ValidationError(_('Bu jadvaldan oʻchirib boʻlmaydi.'))

    model, _fields = EDITABLE[kind]
    row = model.objects.filter(pk=pk).first()
    if row is None:
        raise ValidationError(_('Topilmadi.'))

    name = getattr(row, 'name', str(row))
    # The file goes with the row; nothing else will ever read it again.
    picture = getattr(row, 'image', None)
    try:
        row.delete()
    except ProtectedError:
        raise ValidationError(_('Bundan foydalanilmoqda — avval boʻshating.'))
    if picture:
        picture.delete(save=False)
    return name
