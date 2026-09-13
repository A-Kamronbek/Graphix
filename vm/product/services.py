"""Catalogue operations that change data: for now, the heart.

One heart does two things — it saves the product to the visitor's own list and
it moves the public count (§17 #3) — so both have to happen together or not at
all, which is why this lives in a service rather than in the view.
"""
from django.db import transaction
from django.db.models import F

from .models import Product, ProductLike


@transaction.atomic
def toggle_like(user, product):
    """Add or remove ``user``'s like of ``product``; return (liked, count).

    ``get_or_create`` rather than an existence check: the row has a unique
    constraint on (user, product), and two tabs tapping the heart at the same
    moment would otherwise race into an IntegrityError.

    The count moves with an ``F()`` expression inside the same transaction, so
    a concurrent like can't be lost to a read-modify-write. Removing one is
    guarded by ``likes_count__gt=0``: ``likes_count`` is a PositiveIntegerField
    and a stray decrement past zero is a database error, not a wrong number.
    """
    like, created = ProductLike.objects.get_or_create(user=user, product=product)
    if created:
        Product.objects.filter(pk=product.pk).update(likes_count=F('likes_count') + 1)
    else:
        ProductLike.objects.filter(pk=like.pk).delete()
        Product.objects.filter(pk=product.pk, likes_count__gt=0).update(
            likes_count=F('likes_count') - 1
        )

    # Read back rather than computing: the value the customer sees should be the
    # value in the column, including any concurrent like that landed alongside.
    count = Product.objects.values_list('likes_count', flat=True).get(pk=product.pk)
    return created, count
