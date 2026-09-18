"""Turn two fixed lists into tables, without losing a row.

``Tag.kind`` and ``Product.print_method`` were ``TextChoices``: adding a value
meant a migration, which is the thing the panel exists to avoid (§9 Phase 7
items 7–8). They become tables here, seeded with exactly the values that were
in the code, so every existing tag and product keeps the label it had.

The swap is done with a temporary column rather than a drop-and-add, because a
drop-and-add loses the data: the new column is filled from the old one while
both exist, and only then is the old one removed. Reversible in the same shape.

``Product.fit`` is NOT in here. Two cuts is a decision the owner made (§17 #70)
and a chart finds its products through that field; it stays choices.
"""
import django.db.models.deletion
from django.db import migrations, models

#: What the code said, in the order the shop's filters showed them.
TAG_KINDS = [
    ('style', 'Uslub', 'Стиль', 'Style', 10),
    ('theme', 'Mavzu', 'Тема', 'Theme', 20),
    ('collection', 'Kolleksiya', 'Коллекция', 'Collection', 30),
]

PRINT_METHODS = [
    ('dtf', 'DTF', 'DTF', 'DTF', 10),
    ('dtg', 'DTG', 'DTG', 'DTG', 20),
    ('silkscreen', 'Trafaret', 'Шелкография', 'Silkscreen', 30),
    ('embroidery', 'Naqsh', 'Вышивка', 'Embroidery', 40),
]


def seed(apps, schema_editor):
    """Write the rows the code used to hold."""
    TagKind = apps.get_model('product', 'TagKind')
    PrintMethod = apps.get_model('product', 'PrintMethod')
    for slug, name, name_ru, name_en, order in TAG_KINDS:
        TagKind.objects.update_or_create(
            slug=slug,
            defaults={'name': name, 'name_ru': name_ru, 'name_en': name_en,
                      'order': order})
    for slug, name, name_ru, name_en, order in PRINT_METHODS:
        PrintMethod.objects.update_or_create(
            slug=slug,
            defaults={'name': name, 'name_ru': name_ru, 'name_en': name_en,
                      'order': order})


def unseed(apps, schema_editor):
    """Nothing: the tables are dropped by the reverse of CreateModel."""


def link(apps, schema_editor):
    """Point every tag and product at the row matching the string it held."""
    Tag = apps.get_model('product', 'Tag')
    Product = apps.get_model('product', 'Product')
    TagKind = apps.get_model('product', 'TagKind')
    PrintMethod = apps.get_model('product', 'PrintMethod')

    kinds = {k.slug: k.pk for k in TagKind.objects.all()}
    for tag in Tag.objects.all():
        Tag.objects.filter(pk=tag.pk).update(kind_ref_id=kinds.get(tag.kind))

    methods = {m.slug: m.pk for m in PrintMethod.objects.all()}
    for product in Product.objects.exclude(print_method=''):
        Product.objects.filter(pk=product.pk).update(
            print_ref_id=methods.get(product.print_method))


def unlink(apps, schema_editor):
    """Write the slug back into the character column, for a clean reverse."""
    Tag = apps.get_model('product', 'Tag')
    Product = apps.get_model('product', 'Product')
    for tag in Tag.objects.select_related('kind_ref'):
        Tag.objects.filter(pk=tag.pk).update(
            kind=tag.kind_ref.slug if tag.kind_ref_id else 'theme')
    for product in Product.objects.select_related('print_ref'):
        Product.objects.filter(pk=product.pk).update(
            print_method=product.print_ref.slug if product.print_ref_id else '')


class Migration(migrations.Migration):

    dependencies = [('product', '0018_size_ordering')]

    operations = [
        migrations.CreateModel(
            name='TagKind',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=30, unique=True)),
                ('name', models.CharField(help_text='Oʻzbekcha — asosiy matn',
                                          max_length=60)),
                ('name_ru', models.CharField(blank=True, default='', max_length=60)),
                ('name_en', models.CharField(blank=True, default='', max_length=60)),
                ('order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'verbose_name': 'Teg turi', 'verbose_name_plural': 'Teg turlari',
                     'ordering': ['order', 'slug']},
        ),
        migrations.CreateModel(
            name='PrintMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=30, unique=True)),
                ('name', models.CharField(help_text='Oʻzbekcha — asosiy matn',
                                          max_length=60)),
                ('name_ru', models.CharField(blank=True, default='', max_length=60)),
                ('name_en', models.CharField(blank=True, default='', max_length=60)),
                ('order', models.PositiveSmallIntegerField(default=0)),
            ],
            options={'verbose_name': 'Bosma usuli', 'verbose_name_plural': 'Bosma usullari',
                     'ordering': ['order', 'slug']},
        ),
        migrations.RunPython(seed, unseed),

        # Both columns exist side by side for exactly three operations.
        migrations.AlterModelOptions(name='tag', options={'ordering': ['slug']}),
        migrations.AddField(
            model_name='tag', name='kind_ref',
            field=models.ForeignKey(blank=True, null=True, related_name='tags',
                                    on_delete=django.db.models.deletion.PROTECT,
                                    to='product.tagkind'),
        ),
        migrations.AddField(
            model_name='product', name='print_ref',
            field=models.ForeignKey(blank=True, null=True, related_name='products',
                                    on_delete=django.db.models.deletion.PROTECT,
                                    to='product.printmethod'),
        ),
        migrations.RunPython(link, unlink),

        migrations.RemoveField(model_name='tag', name='kind'),
        migrations.RemoveField(model_name='product', name='print_method'),
        migrations.RenameField(model_name='tag', old_name='kind_ref', new_name='kind'),
        migrations.RenameField(model_name='product', old_name='print_ref',
                               new_name='print_method'),
        migrations.AlterModelOptions(name='tag', options={'ordering': ['kind', 'slug']}),
    ]
