"""Filter groups and items the owner manages (§17 #404, §9 Phase 23 part G).

Two new tables and a link from products to items; nothing existing changes.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0030_chart_names"),
    ]

    operations = [
        migrations.CreateModel(
            name="FilterGroup",
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
                    "name",
                    models.CharField(
                        help_text="Oʻzbekcha — asosiy matn", max_length=60
                    ),
                ),
                ("name_ru", models.CharField(blank=True, default="", max_length=60)),
                ("name_en", models.CharField(blank=True, default="", max_length=60)),
                ("slug", models.SlugField(max_length=60, unique=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["sort_order", "pk"],
            },
        ),
        migrations.CreateModel(
            name="FilterItem",
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
                    "name",
                    models.CharField(
                        help_text="Oʻzbekcha — asosiy matn", max_length=60
                    ),
                ),
                ("name_ru", models.CharField(blank=True, default="", max_length=60)),
                ("name_en", models.CharField(blank=True, default="", max_length=60)),
                ("slug", models.SlugField(max_length=60)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("colour", models.CharField(blank=True, default="", max_length=7)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="product.filtergroup",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "pk"],
            },
        ),
        migrations.AddField(
            model_name="product",
            name="filter_items",
            field=models.ManyToManyField(
                blank=True, related_name="products", to="product.filteritem"
            ),
        ),
        migrations.AddConstraint(
            model_name="filteritem",
            constraint=models.UniqueConstraint(
                fields=("group", "slug"), name="filter_item_slug_in_group"
            ),
        ),
    ]
