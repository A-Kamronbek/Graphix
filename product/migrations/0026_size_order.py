"""Give a size a place in the order sizes are sold in.

Sizes were ordered by id, the order they were added in. That was the right
order only while they were added smallest first, and the owner added XS after
XL: every size picker on the site read S, M, L, XL, XS (§17 #358).

This adds the column and the ordering. The sizes that exist are placed by the
migration after this one, because a data migration and a schema change on the
same table are two migrations (§4.2).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0025_slide_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='size',
            name='order',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AlterModelOptions(
            name='size',
            options={'ordering': ['order', 'id']},
        ),
    ]
