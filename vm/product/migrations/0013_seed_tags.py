"""Seed the starting tag taxonomy from plan §7.

Only the two ``style`` and six ``theme`` tags the plan names. No ``collection``
tags: those are per-drop and the owner creates them as drops happen. Keyed on
``slug`` with ``get_or_create``, so a re-run never overwrites a renamed tag.

Tags — not categories — are what the Phase 13 recommender reads, because every
product here is a t-shirt (§17 #26). The owner is expected to extend this list;
see §19.
"""
from django.db import migrations


TAGS = [
    ('style', 'oversize',   'Oversize',   'Оверсайз',    'Oversize'),
    ('style', 'boxy',       'Boxy',       'Бокси',       'Boxy'),
    ('theme', 'anime',      'Anime',      'Аниме',       'Anime'),
    ('theme', 'streetwear', 'Streetwear', 'Стритвир',    'Streetwear'),
    ('theme', 'music',      'Musiqa',     'Музыка',      'Music'),
    ('theme', 'sport',      'Sport',      'Спорт',       'Sport'),
    ('theme', 'minimal',    'Minimal',    'Минимализм',  'Minimal'),
    ('theme', 'vintage',    'Vintage',    'Винтаж',      'Vintage'),
]


def seed(apps, schema_editor):
    Tag = apps.get_model('product', 'Tag')
    for kind, slug, name, name_ru, name_en in TAGS:
        Tag.objects.get_or_create(
            slug=slug,
            defaults={'kind': kind, 'name': name, 'name_ru': name_ru, 'name_en': name_en},
        )


def unseed(apps, schema_editor):
    """Remove the seeded tags, but never one already attached to a product."""
    Tag = apps.get_model('product', 'Tag')
    Tag.objects.filter(slug__in=[t[1] for t in TAGS], products__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0012_alter_category_slug_alter_product_slug'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
