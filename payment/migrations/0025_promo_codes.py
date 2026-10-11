"""Promo codes, and what an order freezes about its own (§17 #310).

Nothing existing is rewritten: every order placed before this has no code and
a discount of 0, so its total still reads goods plus delivery.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0024_delivery_days"),
        ("product", "0025_slide_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="discount",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name="order",
            name="discount_product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="product.product",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="promo_code",
            field=models.CharField(blank=True, default="", max_length=24),
        ),
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(max_length=24, unique=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("product_sum", "Bitta mahsulotdan summa"),
                            ("product_percent", "Bitta mahsulotdan foiz"),
                            ("order_sum", "Buyurtmadan summa"),
                            ("order_percent", "Buyurtmadan foiz"),
                            ("free_delivery", "Bepul yetkazib berish"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "value",
                    models.DecimalField(decimal_places=0, default=0, max_digits=15),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("max_uses", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "min_subtotal",
                    models.DecimalField(decimal_places=0, default=0, max_digits=15),
                ),
                ("once_per_customer", models.BooleanField(default=True)),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "products",
                    models.ManyToManyField(
                        blank=True, related_name="promo_codes", to="product.product"
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="order",
            name="promo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="payment.promocode",
            ),
        ),
    ]
