# Generated for GRAPHIX — remove unreachable ACTIVE status; default is now PAYING.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0007_order_notes_payment_method'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('paying', "To'lanmoqda"),
                    ('paid', "To'langan"),
                    ('processing', 'Jarayonda'),
                    ('on_the_way', "Yo'lda"),
                    ('done', 'Bajarildi'),
                    ('cancelled', 'Bekor qilindi'),
                ],
                db_index=True,
                default='paying',
                max_length=50,
            ),
        ),
    ]
