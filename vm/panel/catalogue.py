"""Creating and editing a product from the panel.

This is the screen the plan calls the most important one in the phase, because
the owner adds every product himself, from a phone, with photographs. So the
work lives here rather than in a view: four things have to change together —
the product row, its translations, its photographs and its size/stock grid —
and a half-saved product is a product that is live on the storefront with no
price on one size.

Three things are deliberately hidden from the owner and handled here:

* **colour.** Every design ships in one colourway, so the storefront renders no
  picker (§17 #23) and neither does the panel. Every variant gets
  ``default_colour()`` silently.
* **the slug.** Derived from the Uzbek name on first save and then never
  touched, because it is the product's permanent URL (§4: paths may change,
  with a 301; they do not change by accident).
* **image order.** The owner drags; the numbers are ours.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _

from product import images as image_pipeline
from product.models import (Category, ImageP, PrintMethod, Product, Size,
                            SizeChart, Tag, Variant, default_colour)

#: Photographs per product. The storefront's gallery is built around four —
#: which is what the Definition of Done asks to be creatable in one sitting —
#: and the ceiling is twice that, so a drop with a couple of detail shots and a
#: size reference does not run out of room.
MAX_IMAGES = 8

#: The shape every product description follows (plan §9 Phase 8 item 7), so
#: the catalogue keeps one voice as it grows. Four parts, one per line. The
#: spec strip already prints the fabric, the weight and the print method from
#: their own fields, so the template does not ask for them a second time - a
#: fact written twice is a fact that will disagree with itself (§17 #111).
#: The brackets are what the owner replaces; docs/content/product-copy.md
#: explains each part (§17 #197).
DESCRIPTION_TEMPLATE = (
    _('Dizayn: [nima tasvirlangan va nimadan ilhomlangan — bir-ikki gap]'),
    _('Bosma: [qayerda — old, orqa yoki ikkala tomonda; taxminiy oʻlchami, sm]'),
    _('Bichim: [qanday oʻtiradi — oddiy yoki keng; oʻlcham tanlash boʻyicha maslahat]'),
    _('Parvarish: 30 °C da, teskari tomonidan yuving. Bosma ustidan dazmollamang. '
      'Oqartiruvchi ishlatmang, mashinada quritmang.'),
)


def description_templates():
    """The template in the language of each description box.

    The screen's own language does not decide it: the Russian box wants the
    Russian template even while the panel around it is in Uzbek.
    """
    from django.utils import translation
    out = {}
    for field, lang in (('description', 'uz'), ('description_ru', 'ru'),
                        ('description_en', 'en')):
        with translation.override(lang):
            out[field] = '\n\n'.join(str(part) for part in DESCRIPTION_TEMPLATE)
    return out


class Refused(ValidationError):
    """Something the owner sent cannot be saved, with a sentence saying why."""


def _decimal(raw, field):
    """Parse a price. Blank is not zero — zero is a price, blank is a mistake.

    Rounds half up rather than to even, for the same reason the rest of the
    project does: 2500.5 soʻm is 2501, and Python's default would make it 2500
    while making 2501.5 into 2502 (§17, Phase 12).
    """
    try:
        value = Decimal(str(raw).strip().replace(' ', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise Refused(_('“%(field)s” uchun notoʻgʻri narx.') % {'field': field})
    if value < 0:
        raise Refused(_('Narx manfiy boʻlishi mumkin emas.'))
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def price_of(raw):
    """Parse a price from an inline edit on the list. Raises :class:`Refused`."""
    return _decimal(raw, _('Narx'))


def _int(raw, default=0):
    """Read a whole number out of the form. Never negative, never raises.

    For the fields where a wrong number is only a wrong number — the GSM box,
    an image id. The grid's stock boxes do NOT use this; see :func:`_count`.
    """
    try:
        return max(0, int(str(raw).strip() or default))
    except (TypeError, ValueError):
        return default


def _count(raw, field):
    """Read a stock count, refusing anything that is not one.

    ``_int`` turns "sa" into 0, which is the worst answer available: the size
    goes out of stock, the storefront stops selling it, and nothing on the
    screen says why. A count somebody mistyped is a question, not a zero.
    """
    # A missing box is not a wrong one: a size priced with nothing typed in its
    # stock box has a stock of zero, which is what "none left yet" means.
    if raw is None:
        return 0
    value = str(raw).strip()
    if not value:
        return 0
    if not value.isdigit():
        raise Refused(_('“%(field)s” uchun notoʻgʻri zaxira.') % {'field': field})
    return int(value)


def _text(data, name, label):
    """Read one text field, refusing anything longer than its column.

    The form carries `maxlength` on every one of these, so the only way to get
    here with an over-long value is a POST that did not come from the screen —
    but "did not come from the screen" is exactly when a 500 is least useful,
    and Postgres refuses an over-long value with one.
    """
    value = (data.get(name) or '').strip()
    limit = Product._meta.get_field(name).max_length
    if limit and len(value) > limit:
        raise Refused(_('“%(field)s” juda uzun — koʻpi bilan %(n)d ta belgi.')
                      % {'field': label, 'n': limit})
    return value


@transaction.atomic
def save_product(data, product=None):
    """Create or update a product from the panel form's POST. Returns it.

    Everything in one transaction: a product whose photographs saved and whose
    grid did not would be live on the storefront and unbuyable.
    """
    name = _text(data, 'name', _('Nomi'))
    if not name:
        raise Refused(_('Nomi kerak.'))

    product = product or Product()
    product.name = name
    product.name_ru = _text(data, 'name_ru', _('Nomi'))
    product.name_en = _text(data, 'name_en', _('Nomi'))
    product.description = (data.get('description') or '').strip()
    product.description_ru = (data.get('description_ru') or '').strip()
    product.description_en = (data.get('description_en') or '').strip()

    category_id = data.get('category') or ''
    product.category = (Category.objects.filter(pk=category_id).first()
                        if category_id.isdigit() else None)

    chart_id = data.get('size_chart') or ''
    product.size_chart = (SizeChart.objects.filter(pk=chart_id).first()
                          if chart_id.isdigit() else None)

    # The spec strip. Structured on purpose, so it renders consistently instead
    # of being buried in prose in the description.
    gsm = (data.get('gsm') or '').strip()
    product.gsm = _int(gsm) or None if gsm else None
    product.material = _text(data, 'material', _('Mato'))
    product.material_ru = _text(data, 'material_ru', _('Mato'))
    product.material_en = _text(data, 'material_en', _('Mato'))

    method_id = (data.get('print_method') or '').strip()
    product.print_method = (PrintMethod.objects.filter(pk=method_id).first()
                            if method_id.isdigit() else None)

    # At least one tag, read before anything is written. Tags are what the
    # shop's filters and the Phase 13 recommender work from, and a product
    # without one is invisible to both (§12 risk #22, §17 #228).
    # `getlist` on a QueryDict; a plain dict in a test gets a list back.
    wanted = data.getlist('tags') if hasattr(data, 'getlist') else data.get('tags', [])
    tags = list(Tag.objects.filter(pk__in=[t for t in wanted if str(t).isdigit()]))
    if not tags:
        raise Refused(_('Kamida bitta teg tanlang.'))

    product.is_active = bool(data.get('is_active'))
    product.save()
    product.tags.set(tags)
    return product


@transaction.atomic
def save_grid(product, data):
    """Write the size × stock × price grid, creating and removing variants.

    A size with no price is a size the product is not made in, and its variant
    is **deleted** rather than left at zero — an empty row in the grid should
    mean the size disappears from the product page, which is what the owner
    expects when they clear it.

    A variant that a customer has already ordered cannot be deleted (the cart
    line points at it under ``PROTECT``), so one that cannot go is switched off
    instead. Losing the history of what somebody bought to tidy a form is not a
    trade worth making.
    """
    colour = default_colour()
    seen = []

    for size in Size.objects.all():
        raw_price = (data.get('price_%s' % size.pk) or '').strip()
        if not raw_price:
            continue
        price = _decimal(raw_price, size.size)
        stock = _count(data.get('stock_%s' % size.pk), size.size)
        available = bool(data.get('available_%s' % size.pk))

        variant, _created = Variant.objects.update_or_create(
            product=product, size=size, colour=colour,
            defaults={'price': price, 'stock': stock, 'available': available},
        )
        seen.append(variant.pk)

    if not seen:
        raise Refused(_('Kamida bitta oʻlcham uchun narx kiriting.'))

    for variant in product.variants.exclude(pk__in=seen):
        try:
            variant.delete()
        except ProtectedError:
            # An order's cart line points at it. Switch it off and keep the
            # row, so the order still knows what was bought. Caught by name
            # rather than by `Exception`: Django raises this one before it
            # sends any SQL, so the surrounding transaction is still usable —
            # a bare catch would have swallowed the errors that are not.
            Variant.objects.filter(pk=variant.pk).update(available=False, stock=0)
    return len(seen)


@transaction.atomic
def add_images(product, uploads):
    """Sanitise and attach photographs, appending after the ones already there.

    Through the same pipeline as a customer's review photo — resized, re-encoded
    and stripped of EXIF. The owner's own phone writes GPS into a photograph
    just as a customer's does, and a shop's address is not a secret but a
    photographer's home is.
    """
    existing = product.images.count()
    if existing + len(uploads) > MAX_IMAGES:
        raise Refused(_('Koʻpi bilan %(n)d ta rasm.') % {'n': MAX_IMAGES})

    made = []
    for index, upload in enumerate(uploads):
        clean = image_pipeline.sanitise(
            upload, name_hint='%s-%d' % (product.slug or 'mahsulot', existing + index + 1),
            max_edge=image_pipeline.PRODUCT_MAX_EDGE)
        made.append(ImageP.objects.create(product=product, picture=clean,
                                          order=existing + index))
    return made


@transaction.atomic
def reorder_images(product, ids):
    """Renumber this product's photographs into the order given.

    Only ids that belong to this product are honoured, and anything the caller
    left out keeps its place at the end — a drag that arrives with a stale list
    must not silently drop a photograph.
    """
    mine = {image.pk: image for image in product.images.all()}
    position = 0
    for raw in ids:
        image = mine.pop(_int(raw, -1), None)
        if image is not None:
            ImageP.objects.filter(pk=image.pk).update(order=position)
            position += 1
    for image in mine.values():
        ImageP.objects.filter(pk=image.pk).update(order=position)
        position += 1
    return position
