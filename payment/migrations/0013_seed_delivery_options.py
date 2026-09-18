"""Seed the two delivery tiers the shop offers (plan §7).

They are rows rather than constants so the owner can change a price or switch a
tier off from the admin without a deploy. ``get_or_create`` keyed on ``code``
means a re-run never overwrites an edit the owner has since made.

Copy is written in all three languages, not machine-translated: Uzbek is the
source, Russian is in normal commercial register, English reads naturally.
"""
from decimal import Decimal

from django.db import migrations


OPTIONS = [
    {
        'code': 'uzpost_office',
        'name': 'Pochta boʻlimiga',
        'name_ru': 'До отделения почты',
        'name_en': 'To a post office branch',
        'note': 'Buyurtmani oʻzingiz tanlagan Oʻzbekiston pochtasi boʻlimidan olib ketasiz.',
        'note_ru': 'Заказ можно забрать в выбранном вами отделении «Узбекистон почтаси».',
        'note_en': 'Collect the order from whichever Uzbekiston pochtasi branch you choose.',
        'price': Decimal('15000'),
        'requires_pickup_point': True,
        'sort_order': 10,
    },
    {
        'code': 'uzpost_door',
        'name': 'Eshikkacha yetkazib berish',
        'name_ru': 'Доставка до двери',
        'name_en': 'Delivery to your door',
        'note': 'Kuryer buyurtmani siz koʻrsatgan manzilga olib boradi.',
        'note_ru': 'Курьер доставит заказ по указанному вами адресу.',
        'note_en': 'A courier brings the order to the address you give.',
        'price': Decimal('30000'),
        'requires_pickup_point': False,
        'sort_order': 20,
    },
]


def seed(apps, schema_editor):
    DeliveryOption = apps.get_model('payment', 'DeliveryOption')
    for row in OPTIONS:
        DeliveryOption.objects.get_or_create(code=row['code'], defaults=row)


def unseed(apps, schema_editor):
    """Remove the seeded tiers, but never one a real order points at (PROTECT)."""
    DeliveryOption = apps.get_model('payment', 'DeliveryOption')
    codes = [row['code'] for row in OPTIONS]
    DeliveryOption.objects.filter(code__in=codes, orders__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0012_alter_order_order_no'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
