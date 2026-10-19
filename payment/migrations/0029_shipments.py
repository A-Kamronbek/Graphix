"""Uzpost shipments and the statuses the shop has seen them in (§17 #379, #380).

Two new tables and nothing else: no order is touched.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0028_uzpost_ids"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Shipment",
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
                ("uzpost_id", models.PositiveBigIntegerField(blank=True, null=True, unique=True)),
                ("number", models.CharField(blank=True, db_index=True, default="", max_length=40)),
                ("service", models.CharField(max_length=40)),
                ("weight", models.DecimalField(decimal_places=3, max_digits=6)),
                (
                    "transportation",
                    models.CharField(blank=True, default="", max_length=12),
                ),
                (
                    "office_index",
                    models.CharField(blank=True, default="", max_length=10),
                ),
                (
                    "office_name",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                ("status", models.CharField(blank=True, default="", max_length=40)),
                ("status_at", models.DateTimeField(blank=True, null=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                (
                    "reported_status",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shipments",
                        to="payment.order",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ShipmentStatus",
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
                ("status", models.CharField(max_length=40)),
                ("at", models.DateTimeField()),
                ("seen_at", models.DateTimeField(auto_now_add=True)),
                (
                    "shipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="payment.shipment",
                    ),
                ),
            ],
            options={
                "ordering": ["-at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="shipment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("cancelled_at__isnull", True)),
                fields=("order",),
                name="payment_one_live_shipment_per_order",
            ),
        ),
    ]
