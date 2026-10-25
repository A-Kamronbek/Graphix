"""Suggested designs and their pictures (§17 #402, §9 Phase 23 part E).

Two new tables and nothing else.
"""

import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_msg_is_read"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DesignRequest",
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
                ("idea", models.TextField()),
                (
                    "print_text",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                (
                    "garment",
                    models.CharField(
                        choices=[("tshirt", "Futbolka"), ("longsleeve", "Longsliv")],
                        max_length=12,
                    ),
                ),
                (
                    "colour",
                    models.CharField(
                        choices=[
                            ("white", "Oq"),
                            ("black", "Qora"),
                            ("grey", "Kulrang"),
                            ("other", "Boshqa rang"),
                        ],
                        max_length=8,
                    ),
                ),
                (
                    "colour_other",
                    models.CharField(blank=True, default="", max_length=60),
                ),
                (
                    "print_colours",
                    models.CharField(blank=True, default="", max_length=32),
                ),
                (
                    "placement",
                    models.CharField(
                        choices=[
                            ("front", "Old tomonga"),
                            ("back", "Orqa tomonga"),
                            ("both", "Ikkala tomonga"),
                        ],
                        max_length=8,
                    ),
                ),
                ("size", models.CharField(max_length=20)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("phone", models.CharField(max_length=25)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="design_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DesignImage",
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
                ("picture", models.ImageField(upload_to=core.models.design_photo_path)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="core.designrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
    ]
