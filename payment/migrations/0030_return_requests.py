"""Return and exchange requests (§17 #399, §9 Phase 23 part B).

Three new tables and nothing else: no order, line or size is touched.
"""

import django.core.validators
import django.db.models.deletion
import payment.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0005_remove_cart_unique_open_cart_per_user_and_more"),
        ("payment", "0029_shipments"),
        ("product", "0030_chart_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReturnRequest",
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
                (
                    "kind",
                    models.CharField(
                        choices=[("return", "Qaytarish"), ("exchange", "Almashtirish")],
                        max_length=10,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("size", "Oʻlcham mos kelmadi"),
                            ("fault", "Mahsulotda nuqson bor"),
                            ("wrong", "Boshqa mahsulot yuborilgan"),
                            ("not_as_described", "Saytdagi tavsifga mos emas"),
                            ("other", "Boshqa sabab"),
                        ],
                        max_length=20,
                    ),
                ),
                ("explanation", models.TextField()),
                (
                    "phone",
                    models.CharField(
                        max_length=20,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="format: +998 XX XXX XX XX",
                                regex="^\\+998 ?\\d{2} ?\\d{3} ?\\d{2} ?\\d{2}$",
                            )
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Yangi"),
                            ("reviewing", "Koʻrib chiqilmoqda"),
                            ("accepted", "Qabul qilindi"),
                            ("rejected", "Rad etildi"),
                            ("done", "Yakunlandi"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=10,
                    ),
                ),
                ("answer", models.TextField(blank=True, default="")),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "closed_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "answered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="answered_returns",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_requests",
                        to="payment.order",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="return_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ReturnLine",
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
                ("quantity", models.PositiveSmallIntegerField()),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_lines",
                        to="cart.cartitem",
                    ),
                ),
                (
                    "size_wanted",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="product.size",
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="payment.returnrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="ReturnImage",
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
                (
                    "width",
                    models.PositiveIntegerField(blank=True, editable=False, null=True),
                ),
                (
                    "height",
                    models.PositiveIntegerField(blank=True, editable=False, null=True),
                ),
                (
                    "renditions",
                    models.JSONField(blank=True, default=dict, editable=False),
                ),
                (
                    "picture",
                    models.ImageField(upload_to=payment.models.return_photo_path),
                ),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="payment.returnrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
    ]
