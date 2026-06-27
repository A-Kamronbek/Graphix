# Generated for ValleyMade — persist checkout notes and payment method.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0006_alter_order_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='notes',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('click', 'Click'), ('cash', 'Naqd pul')],
                default='click',
                max_length=20,
            ),
        ),
    ]
