"""A size chart's name in Russian and English (§17 #400).

Two empty columns beside the Uzbek name, read where there are several charts
to tell apart, in the page's language, defaulting to empty in the database
too. No row is touched; the name's help text is the only change to an
existing column.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0029_chart_for_the_rest"),
    ]

    operations = [
        migrations.AddField(
            model_name="sizechart",
            name="name_en",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=120
            ),
        ),
        migrations.AddField(
            model_name="sizechart",
            name="name_ru",
            field=models.CharField(
                blank=True, db_default="", default="", max_length=120
            ),
        ),
        migrations.AlterField(
            model_name="sizechart",
            name="name",
            field=models.CharField(help_text="Oʻzbekcha — asosiy matn", max_length=120),
        ),
    ]
