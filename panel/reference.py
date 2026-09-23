"""Editing the small reference tables from the panel.

Regions, districts, delivery tiers, payment methods, sizes, tags, tag kinds,
print methods, categories and size charts all change a few times a year: a
district is renamed, a delivery price moves, a new collection tag appears.
These screens mean none of that needs a deploy.

They all have the same shape, so there is one endpoint rather than ten. What
makes a single endpoint safe is the EDITABLE table below: a field not named
there cannot be written, whatever arrives in the POST. Without it, an endpoint
taking a model, a field and a value can set anything on any row, including a
price.

DELETABLE is a second, shorter allowlist. Regions, districts, delivery tiers
and payment methods are left out of it: orders point at all four, and how a
parcel was sent and paid for should survive a tidy-up.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.utils.translation import gettext as _

from payment.models import DeliveryOption, District, PaymentOption, Region
from product.models import (Category, PrintMethod, Size, SizeChart, Slide,
                            Tag, TagKind, slide_link)

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
    # One field, and it is the axis of every product's price-and-stock grid:
    # renaming a size here renames it on every product at once, which is the
    # point of its being a row. Adding one is a new column in that grid.
    'size': (Size, {
        'size': 'text',
    }),
    # How a customer may pay. `code` is deliberately absent: it is what the
    # checkout matches on and what a webhook arrives quoting, so a typo in it
    # would take a payment method off the site with no error anywhere. The
    # switch is `is_active`, which is the whole reason these are rows (§17 #99).
    'payment': (PaymentOption, {
        'name': 'text', 'name_ru': 'text', 'name_en': 'text',
        'note': 'text', 'note_ru': 'text', 'note_en': 'text',
        'is_active': 'bool', 'sort_order': 'count',
    }),
    # A home-page card. `picture` is absent for the same reason a size
    # chart's is: it is a file, set when the slide is created and changed by
    # creating another. `link` gets its own reader rather than 'text' —
    # `set_field` writes with `update_fields` and never runs a model
    # validator, so 'text' here would let `javascript:` through the one box
    # on the panel whose value becomes an `href` on the home page.
    'slide': (Slide, {
        'alt': 'text', 'alt_ru': 'text', 'alt_en': 'text',
        'link': 'link', 'is_active': 'bool', 'sort_order': 'count',
    }),
}

#: Where a row keeps the name a reader would call it by, when that is not a
#: field called ``name``. A size is called "M" and keeps it in ``size``; two
#: sizes called M, or one called nothing, are exactly as bad as they would be
#: for a tag, and both checks below would have missed them.
#:
#: A slide's is ``alt``, and that entry is doing real work: `alt` is the only
#: accessible name a slide has, so blanking it turns a card into an unlabelled
#: link. It is deliberately absent from :data:`UNIQUE_NAMES` — two slides may
#: honestly describe the same thing, and there is nothing to disambiguate.
NAME_FIELD = {'size': 'size', 'slide': 'alt'}

#: What may be removed, and what it costs. Everything here is either unlinked
#: on delete (a tag comes off its products, a chart and a category fall back to
#: null) or protected by the database (a kind or a method that is in use).
#: Anything an order points at is absent on purpose.
#: `size` is here because the database already refuses the dangerous case:
#: `Variant.size` and `SizeChartRow.size` are both PROTECT, so a size any
#: product sells cannot be removed and the panel says so. `payment` is NOT
#: here - an order records the method it was paid by as text, and deleting
#: the row would leave old orders quoting a method the shop can no longer
#: explain. Switching it off is what the switch is for.
#: `slide` is here because a promotion that has run its course should go, and
#: nothing points at one — it is content, not a record of anything. Its file
#: and its renditions go with it, through the same `post_delete` receiver
#: every other photograph uses.
DELETABLE = {'tag', 'tagkind', 'method', 'category', 'chart', 'size', 'slide'}


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


def _link(raw):
    """A slide's destination, checked by the model's own validator.

    Through :func:`~product.models.slide_link` rather than repeating its rule,
    because two copies of "what counts as a safe href" is one copy that will
    be relaxed later without the other noticing. `set_field` saves with
    ``update_fields``, which runs no validators at all, so this reader is the
    only thing standing between the panel's box and the home page's `href`.
    """
    value = str(raw).strip()
    slide_link(value)
    return value


def _count(raw):
    """A whole number of items, never negative. Blank counts as zero."""
    try:
        return max(0, int(str(raw).strip() or 0))
    except (TypeError, ValueError):
        raise ValidationError(_('Notoʻgʻri son.'))


#: The lists whose rows must not share a name (§18 #31, §17 #229). A tag is
#: compared only with the tags of its own kind - "Qora" may be a colour and a
#: collection - and the other three with their whole table.
UNIQUE_NAMES = {'tag', 'tagkind', 'method', 'category', 'size', 'payment'}


def refuse_duplicate(table, name, tag_kind=None, exclude_pk=None):
    """Raise if another row of ``table`` already has this Uzbek name.

    Letter case is ignored: "Anime" and "anime" are the same chip to a
    shopper. Two identical chips in one filter group are a question the owner
    would have to answer later, so the form answers it now. ``tag_kind`` is
    the kind a tag is being saved under; ``exclude_pk`` is the row being
    renamed, which may keep its own name.
    """
    if table not in UNIQUE_NAMES:
        return
    model = EDITABLE[table][0]
    field = NAME_FIELD.get(table, 'name')
    rows = model.objects.filter(**{field + '__iexact': str(name).strip()})
    if table == 'tag':
        rows = rows.filter(kind=tag_kind)
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    twin = rows.first()
    if twin is not None:
        raise ValidationError(
            _('«%(name)s» nomi bu roʻyxatda allaqachon bor.')
            % {'name': getattr(twin, field)})


READERS = {
    'text': lambda raw: str(raw).strip(),
    'bool': lambda raw: str(raw) in ('1', 'true', 'on'),
    'money': _money,
    'prefix': _prefix,
    'count': _count,
    'tagkind': _tagkind,
    'link': _link,
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
    if field == NAME_FIELD.get(kind, 'name') and not value:
        raise ValidationError(_('Nomi boʻsh boʻlishi mumkin emas.'))

    # A name longer than its column is a validation problem, and it was being
    # answered with a 500: the value went straight to Postgres, which refuses
    # it, and the screen showed "could not save" while the log filled up with
    # tracebacks. A paste is all it takes — none of these boxes is longer than
    # 255 characters and none of them said so.
    limit = getattr(model._meta.get_field(field), 'max_length', None)
    if limit and isinstance(value, str) and len(value) > limit:
        raise ValidationError(
            _('Juda uzun — koʻpi bilan %(n)d ta belgi.') % {'n': limit})

    # A rename, or a tag moved to another kind, must not produce the twin the
    # create form refuses (§17 #229).
    if field == NAME_FIELD.get(kind, 'name'):
        refuse_duplicate(kind, value, tag_kind=getattr(row, 'kind', None),
                         exclude_pk=row.pk)
    elif kind == 'tag' and field == 'kind':
        refuse_duplicate(kind, row.name, tag_kind=value, exclude_pk=row.pk)

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

    name = getattr(row, NAME_FIELD.get(kind, 'name'), None) or str(row)
    # The file goes with the row; nothing else will ever read it again.
    picture = getattr(row, 'image', None)
    try:
        row.delete()
    except ProtectedError:
        raise ValidationError(_('Bundan foydalanilmoqda — avval boʻshating.'))
    if picture:
        picture.delete(save=False)
    return name
