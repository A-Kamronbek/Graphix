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
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from product import images as image_pipeline
from product.models import (Category, ImageP, Product, Size, SizeChart, Tag,
                            Variant, default_colour)

#: Photographs per product. Four is what the storefront's gallery is built for
#: and what the Definition of Done asks to be creatable in one sitting.
MAX_IMAGES = 8


class Refused(ValidationError):
    """Something the owner sent cannot be saved, with a sentence saying why."""


def _decimal(raw, field):
    """Parse a price. Blank is not zero — zero is a price, blank is a mistake."""
    try:
        value = Decimal(str(raw).strip().replace(' ', '').replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise Refused(_('“%(field)s” uchun notoʻgʻri narx.') % {'field': field})
    if value < 0:
        raise Refused(_('Narx manfiy boʻlishi mumkin emas.'))
    return value.quantize(Decimal('1'))


def price_of(raw):
    """Parse a price from an inline edit on the list. Raises :class:`Refused`."""
    return _decimal(raw, _('Narx'))


def _int(raw, default=0):
    try:
        return max(0, int(str(raw).strip() or default))
    except (TypeError, ValueError):
        return default


@transaction.atomic
def save_product(data, product=None):
    """Create or update a product from the panel form's POST. Returns it.

    Everything in one transaction: a product whose photographs saved and whose
    grid did not would be live on the storefront and unbuyable.
    """
    name = (data.get('name') or '').strip()
    if not name:
        raise Refused(_('Nomi kerak.'))

    product = product or Product()
    product.name = name
    product.name_ru = (data.get('name_ru') or '').strip()
    product.name_en = (data.get('name_en') or '').strip()
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
    product.material = (data.get('material') or '').strip()
    product.material_ru = (data.get('material_ru') or '').strip()
    product.material_en = (data.get('material_en') or '').strip()

    method = (data.get('print_method') or '').strip()
    product.print_method = method if method in Product.PrintMethod.values else ''
    fit = (data.get('fit') or '').strip()
    product.fit = fit if fit in Product.Fit.values else ''

    product.is_active = bool(data.get('is_active'))
    product.save()

    # `getlist` on a QueryDict; a plain dict in a test gets a list back.
    wanted = data.getlist('tags') if hasattr(data, 'getlist') else data.get('tags', [])
    product.tags.set(Tag.objects.filter(pk__in=[t for t in wanted if str(t).isdigit()]))
    return product


@transaction.atomic
def save_grid(product, data):
    """Write the size × stock × price grid, creating and removing variants.

    A size with no price is a size the product is not made in, and its variant
    is **deleted** rather than left at zero — an empty row in the grid should
    mean the size disappears from the product page, which is what the owner
    expects when they clear it.

    A variant that a customer has already ordered cannot be deleted (the cart
    line points at it), so one that cannot go is switched off instead. Losing
    the history of what somebody bought to tidy a form is not a trade worth
    making.
    """
    colour = default_colour()
    seen = []

    for size in Size.objects.all():
        raw_price = (data.get('price_%s' % size.pk) or '').strip()
        if not raw_price:
            continue
        price = _decimal(raw_price, size.size)
        stock = _int(data.get('stock_%s' % size.pk))
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
        except Exception:
            # Something points at it — an order's cart line. Switch it off and
            # keep the row, so the order still knows what was bought.
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
