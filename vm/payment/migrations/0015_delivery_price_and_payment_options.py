"""Home delivery becomes 40 000 so'm, and the payment methods become rows.

**The price.** The owner's decision (§17 #85) put home delivery at 40 000 so'm
nationwide, and the seeded row has said 30 000 since Phase 4 — so the plan and
the site have been disagreeing, and the site is what a customer reads (§18 #18).
This corrects the row; Phase 6e corrects the three places that state the figure
as copy.

The update is conditional on the row still holding the old price. If the owner
has already changed it in the admin, that is a real decision and a migration
must not quietly undo it.

**The payment methods.** Click and cash become rows for the same reason the
delivery tiers are rows (§17 #13): whether the shop takes cash is a commercial
decision, and a commercial decision should not need a deploy. Cash ships
**inactive** — the storefront does not offer it and the checkout refuses it —
and the owner switches it on from the admin if he ever wants it.
"""
from decimal import Decimal

from django.db import migrations


OLD_DOOR_PRICE = Decimal('30000')
NEW_DOOR_PRICE = Decimal('40000')

PAYMENT_OPTIONS = [
    {
        'code': 'click',
        'name': 'Click',
        'name_ru': 'Click',
        'name_en': 'Click',
        'note': 'Kartadan onlayn toʻlov.',
        'note_ru': 'Онлайн-оплата картой.',
        'note_en': 'Pay online by card.',
        'is_active': True,
        'sort_order': 10,
    },
    {
        'code': 'cash',
        'name': 'Naqd pul',
        'name_ru': 'Наличные',
        'name_en': 'Cash',
        'note': 'Buyurtmani olganingizda toʻlaysiz.',
        'note_ru': 'Оплата при получении заказа.',
        'note_en': 'Pay when the order reaches you.',
        'is_active': False,        # off until the owner decides otherwise
        'sort_order': 20,
    },
]


def forwards(apps, schema_editor):
    DeliveryOption = apps.get_model('payment', 'DeliveryOption')
    PaymentOption = apps.get_model('payment', 'PaymentOption')

    DeliveryOption.objects.filter(code='uzpost_door', price=OLD_DOOR_PRICE).update(
        price=NEW_DOOR_PRICE
    )
    for row in PAYMENT_OPTIONS:
        PaymentOption.objects.get_or_create(code=row['code'], defaults=row)


def backwards(apps, schema_editor):
    DeliveryOption = apps.get_model('payment', 'DeliveryOption')
    PaymentOption = apps.get_model('payment', 'PaymentOption')

    DeliveryOption.objects.filter(code='uzpost_door', price=NEW_DOOR_PRICE).update(
        price=OLD_DOOR_PRICE
    )
    PaymentOption.objects.filter(code__in=[r['code'] for r in PAYMENT_OPTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0014_retire_pickup_points'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
