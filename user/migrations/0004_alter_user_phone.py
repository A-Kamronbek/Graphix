"""Put the phone field's "already registered" error through gettext.

The message was a raw Uzbek literal with an ASCII apostrophe, so a Russian or
English visitor who signed up with a number already on file got Uzbek. Wrapping
it in ``gettext_lazy`` changes a field kwarg, which Django deconstructs - hence
a migration for what is only a copy fix. No column changes.
"""
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0003_alter_user_phone'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(error_messages={'unique': 'Ushbu raqam allaqachon roʻyxatdan oʻtgan.'}, max_length=17, unique=True, validators=[django.core.validators.RegexValidator(message='format: +998 XX XXX XX XX', regex='^\\+998 ?\\d{2} ?\\d{3} ?\\d{2} ?\\d{2}$')]),
        ),
    ]
