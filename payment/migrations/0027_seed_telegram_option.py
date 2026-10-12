"""Paying through the shop's admin on Telegram, as a `PaymentOption` row.

Switched on, unlike Payme and Octo in `0022`: it needs no keys, and it is
there for the time a gateway cannot take a payment (§17 #362). The owner
switches it off from Boshqaruv when he no longer wants it offered.

It sorts after the gateways and before cash, so a working gateway is still
the first thing a customer is offered.

The copy is written in all three languages here, for the reason `0022`
gives: a `PaymentOption` carries its own translations in columns.

A row the owner has already made under this code is left as it is.
"""
from django.db import migrations

OPTION = {
    'code': 'telegram',
    'name': 'Telegram admin orqali',
    'name_ru': 'Через администратора в Telegram',
    'name_en': 'Through our Telegram admin',
    # No note: the name says it all, and the pay page says the rest.
    'note': '',
    'note_ru': '',
    'note_en': '',
    'is_active': True,
    'sort_order': 16,
}


def forwards(apps, schema_editor):
    """Add the row, leaving one the owner has already made alone."""
    PaymentOption = apps.get_model('payment', 'PaymentOption')
    PaymentOption.objects.get_or_create(code=OPTION['code'], defaults=OPTION)


def backwards(apps, schema_editor):
    """Remove it again. Orders keep their `payment_method` text either way."""
    PaymentOption = apps.get_model('payment', 'PaymentOption')
    PaymentOption.objects.filter(code=OPTION['code']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0026_telegram_method'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
