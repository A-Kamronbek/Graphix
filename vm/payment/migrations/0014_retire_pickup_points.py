"""Retire the Uzpost branch table and replace it with region + district + index.

There is no public Uzpost branch list to own (§3 research), so Phase 4 shipped a
loader, its validation, its tests and an **empty** CSV — and that empty file had
become the blocker on all of Phase 6. §17 #84 dissolves the dependency instead
of working around it: the customer supplies the one field we could never obtain,
their own postal index, and we own only what is published — the SOATO
administrative divisions.

One migration does the whole change, because the pieces only make sense
together: add Region and District and the order fields that point at them,
rename ``requires_pickup_point`` and ``pickup_snapshot`` to names that describe
what they now hold, then drop the branch foreign key and the table.

**The drop is safe because nothing points at it**: checkout has never set a
pickup point, and the guard below asserts that rather than assuming it. If a row
ever did exist, this migration stops before the destructive half rather than
taking an order's delivery address with it.

PaymentOption arrives here too. Cash is not removed — it ships switched off and
the owner turns it on from the admin if he wants it (§17 #94, amended).
"""
import django.db.models.deletion
from django.db import migrations, models


def assert_no_order_uses_a_pickup_point(apps, schema_editor):
    """Refuse to drop the table if any order still points at a branch."""
    Order = apps.get_model('payment', 'Order')
    stranded = Order.objects.exclude(pickup_point=None).count()
    if stranded:
        raise RuntimeError(
            f"{stranded} order(s) still point at a PickupPoint. Migrate their "
            "region/district/postal_index across before retiring the table — "
            "dropping it now would erase where those parcels were sent."
        )


def noop(apps, schema_editor):
    """Reversing adds nothing back: the check only ever read."""


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0013_seed_delivery_options'),
    ]

    operations = [
        migrations.RunPython(assert_no_order_uses_a_pickup_point, noop),
        migrations.CreateModel(
            name='District',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=8, unique=True)),
                ('name', models.CharField(help_text='Oʻzbekcha — asosiy matn', max_length=80)),
                ('name_ru', models.CharField(blank=True, default='', max_length=80)),
                ('name_en', models.CharField(blank=True, default='', max_length=80)),
                ('kind', models.CharField(choices=[('district', 'Tuman'), ('city', 'Shahar'), ('other', 'Boshqa')], default='district', max_length=10)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'ordering': ['region', 'sort_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='PaymentOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(help_text='Oʻzbekcha — asosiy matn', max_length=120)),
                ('name_ru', models.CharField(blank=True, default='', max_length=120)),
                ('name_en', models.CharField(blank=True, default='', max_length=120)),
                ('note', models.CharField(blank=True, default='', help_text='Oʻzbekcha — asosiy matn', max_length=200)),
                ('note_ru', models.CharField(blank=True, default='', max_length=200)),
                ('note_en', models.CharField(blank=True, default='', max_length=200)),
                ('is_active', models.BooleanField(db_index=True, default=False)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'ordering': ['sort_order', 'code'],
            },
        ),
        migrations.CreateModel(
            name='Region',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=4, unique=True)),
                ('name', models.CharField(help_text='Oʻzbekcha — asosiy matn', max_length=80)),
                ('name_ru', models.CharField(blank=True, default='', max_length=80)),
                ('name_en', models.CharField(blank=True, default='', max_length=80)),
                ('postal_prefix', models.CharField(blank=True, db_index=True, default='', max_length=3)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RemoveField(
            model_name='order',
            name='pickup_point',
        ),
        migrations.RenameField(
            model_name='deliveryoption',
            old_name='requires_pickup_point',
            new_name='requires_branch',
        ),
        migrations.RenameField(
            model_name='order',
            old_name='pickup_snapshot',
            new_name='location_snapshot',
        ),
        migrations.AddField(
            model_name='order',
            name='address_source',
            field=models.CharField(blank=True, choices=[('map', 'Xaritadan'), ('manual', 'Qoʻlda kiritilgan')], default='', max_length=10),
        ),
        migrations.AddField(
            model_name='order',
            name='location_note',
            field=models.CharField(blank=True, default='', max_length=160),
        ),
        migrations.AddField(
            model_name='order',
            name='postal_index',
            field=models.CharField(blank=True, db_index=True, default='', max_length=6),
        ),
        migrations.AddField(
            model_name='order',
            name='district',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='payment.district'),
        ),
        migrations.AddField(
            model_name='district',
            name='region',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='districts', to='payment.region'),
        ),
        migrations.AddField(
            model_name='order',
            name='region',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='payment.region'),
        ),
        migrations.DeleteModel(
            name='PickupPoint',
        ),
        migrations.AlterUniqueTogether(
            name='district',
            unique_together={('region', 'name')},
        ),
    ]
