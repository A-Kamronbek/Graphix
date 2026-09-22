"""Payme and Octo as `PaymentOption` rows, switched off (§9 Phase 14 item 5).

Off, like cash was in `0015`, and for a sharper reason: there are no
credentials yet. A method the owner can see and switch on the moment his keys
arrive is the whole point of these being rows rather than constants
(§17 #99) — and until then the checkout does not offer it and refuses it
server-side if one is POSTed anyway.

The copy is written in all three languages here rather than left for gettext,
because a `PaymentOption` carries its own translations in columns: the owner
edits them from Boshqaruv, and a string in a catalogue would be one he cannot
reach (§17 #99).
"""
from django.db import migrations

PAYMENT_OPTIONS = [
    {
        'code': 'payme',
        'name': 'Payme',
        'name_ru': 'Payme',
        'name_en': 'Payme',
        'note': 'Payme ilovasi yoki kartasi orqali toʻlov.',
        'note_ru': 'Оплата через приложение или карту Payme.',
        'note_en': 'Pay with the Payme app or card.',
        'is_active': False,        # no credentials yet
        'sort_order': 12,
    },
    {
        'code': 'octo',
        'name': 'Octo',
        'name_ru': 'Octo',
        'name_en': 'Octo',
        'note': 'Octo orqali karta bilan toʻlov.',
        'note_ru': 'Оплата картой через Octo.',
        'note_en': 'Pay by card through Octo.',
        'is_active': False,        # no credentials yet
        'sort_order': 14,
    },
]


def forwards(apps, schema_editor):
    """Add the two rows, leaving any the owner has already made alone."""
    PaymentOption = apps.get_model('payment', 'PaymentOption')
    for row in PAYMENT_OPTIONS:
        PaymentOption.objects.get_or_create(code=row['code'], defaults=row)


def backwards(apps, schema_editor):
    """Remove them again. Orders keep their `payment_method` text either way."""
    PaymentOption = apps.get_model('payment', 'PaymentOption')
    PaymentOption.objects.filter(
        code__in=[r['code'] for r in PAYMENT_OPTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0021_alter_order_payment_method'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
