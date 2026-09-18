from collections import defaultdict

from django.db import migrations, models


def dedupe_open_carts(apps, schema_editor):
    """
    Collapse any pre-existing duplicate open carts so AddConstraint can apply.

    For each user with >1 open cart, keep the most recent one and merge the
    others' items into it (summing quantities for shared variants, capped at 99
    to match the app's cart logic), then mark the extras as closed.
    """
    Cart = apps.get_model('cart', 'Cart')

    open_carts = Cart.objects.filter(status=True).order_by('user_id', '-created_at', '-id')
    by_user = defaultdict(list)
    for c in open_carts:
        by_user[c.user_id].append(c)

    for user_id, carts in by_user.items():
        if len(carts) < 2:
            continue

        keeper = carts[0]  # most recent open cart
        keeper_items = {ci.variant_id: ci for ci in keeper.cart_items.all()}

        for dup in carts[1:]:
            for ci in dup.cart_items.all():
                existing = keeper_items.get(ci.variant_id)
                if existing is not None:
                    # Same variant already in keeper -> sum and drop the dupe row.
                    existing.quantity = min(99, existing.quantity + ci.quantity)
                    existing.save(update_fields=['quantity'])
                    ci.delete()
                else:
                    # Move the line to the keeper cart.
                    ci.cart = keeper
                    ci.save(update_fields=['cart'])
                    keeper_items[ci.variant_id] = ci
            dup.status = False
            dup.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('cart', '0003_alter_cartitem_variant'),
    ]

    operations = [
        migrations.RunPython(dedupe_open_carts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(
                condition=models.Q(status=True),
                fields=('user',),
                name='unique_open_cart_per_user',
            ),
        ),
    ]
