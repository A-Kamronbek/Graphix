"""A fifth way to pay: through the shop's admin on Telegram (§17 #362).

Only the list of values the column may hold grows. No order is rewritten, and
the row a customer chooses the method by is added by `0027`, on its own: a
change to a table's shape and a change to its rows are two migrations.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0025_promo_codes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("click", "Click"),
                    ("payme", "Payme"),
                    ("octo", "Octo"),
                    ("cash", "Naqd pul"),
                    ("telegram", "Telegram admin orqali"),
                ],
                default="click",
                max_length=20,
            ),
        ),
    ]
