"""Backfill the catalogue fields added in 0010 so they can be made NOT NULL.

Slugs come from the Uzbek base name; the Uzbek modifier letters (oʻ, gʻ) are
non-ASCII, so ``slugify`` drops them — "Oʻzbek koʻylak" becomes "ozbek-koylak",
which is exactly the URL we want. A name that slugifies to nothing (all
Cyrillic, or only punctuation) falls back to ``mahsulot-<pk>``. Collisions get a
numeric suffix, so this is safe to run against any existing data.

Stock is seeded from the existing ``available`` flag: an available variant gets
10 units, an unavailable one 0. The shop had no stock tracking before, so this
is the only interpretation that preserves what was buyable (plan §9 Phase 4).
"""
from django.db import migrations
from django.utils.text import slugify


def _unique_slug(base, taken, pk, prefix):
    """Return a slug not already in ``taken``, adding -2, -3 … on collision."""
    base = base or f"{prefix}-{pk}"
    slug = base[:255]
    n = 2
    while slug in taken:
        suffix = f"-{n}"
        slug = f"{base[:255 - len(suffix)]}{suffix}"
        n += 1
    taken.add(slug)
    return slug


def populate(apps, schema_editor):
    Category = apps.get_model('product', 'Category')
    Product = apps.get_model('product', 'Product')
    Variant = apps.get_model('product', 'Variant')

    taken = set()
    for cat in Category.objects.order_by('pk'):
        if cat.slug:
            taken.add(cat.slug)
    for cat in Category.objects.filter(slug__isnull=True).order_by('pk'):
        cat.slug = _unique_slug(slugify(cat.name), taken, cat.pk, 'kategoriya')
        cat.save(update_fields=['slug'])

    taken = set()
    for prod in Product.objects.order_by('pk'):
        if prod.slug:
            taken.add(prod.slug)
    for prod in Product.objects.filter(slug__isnull=True).order_by('pk'):
        prod.slug = _unique_slug(slugify(prod.name), taken, prod.pk, 'mahsulot')
        prod.save(update_fields=['slug'])

    Variant.objects.filter(available=True).update(stock=10)
    Variant.objects.filter(available=False).update(stock=0)


def unpopulate(apps, schema_editor):
    """Clear the slugs again so 0010 can be unapplied. Stock is left alone."""
    apps.get_model('product', 'Category').objects.update(slug=None)
    apps.get_model('product', 'Product').objects.update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0010_productlike_review_reviewimage_sizechart_and_more'),
    ]

    operations = [
        migrations.RunPython(populate, unpopulate),
    ]
