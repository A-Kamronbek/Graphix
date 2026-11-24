"""Recommendations by tag overlap (plan §9 Phase 13, §3 "Recommendations").

Deliberately not machine learning: with a few hundred designs and a young
shop, counting shared tags is one statement, needs no dependency, and is
useful. Tags are hidden from shoppers and are the owner's (§17 #304); every
product carries at least one (§17 #228).

Three things live here:

* ``order`` puts a list of designs in the order "Siz uchun" shows them to one
  visitor: the designs sharing the most tags with what they have liked first,
  then the shop's most-liked order. A guest, or a visitor with no likes, gets
  the most-liked order alone, which is what the row showed before this phase
  (§17 #420), so the row is never empty.
* ``similar`` is the strip on a product's page: the designs sharing the most
  tags with that one. It needs no history.
* ``shown`` and ``clicked`` count the rows a signed-in visitor is shown and the
  designs opened from them, a day at a time, so the recommender can be held
  against the most-liked list it replaced (``recommend_report``).
"""
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, Exists, F, IntegerField, OuterRef, Value, When
from django.utils import timezone

from .models import Product, ProductLike, RowStat, Variant

#: How long one visitor's scores are kept. A like or an unlike drops them at
#: once (``forget``); a purchase is noticed within the hour.
TTL = 60 * 60

#: The rows that are counted, by the letters their links carry in ``?r=``.
FOR_YOU = 'fy'    # "Siz uchun", ordered by the visitor's likes
POPULAR = 'pl'    # "Siz uchun" in the most-liked order: the baseline
SIMILAR = 'sm'    # the strip on a product's page
ROWS = (FOR_YOU, POPULAR, SIMILAR)

#: Orders whose designs the customer has, so they are not offered again.
BOUGHT = ('paid', 'processing', 'on_the_way', 'done')


def _key(user):
    return 'recommend:%d' % user.pk


def scores(user):
    """``{product id: score}`` for one visitor, from the cache or one statement.

    A design's score is the number of tags it shares with the designs the
    visitor has liked, counted once for each liked design that carries the
    tag: two liked designs with the tag weigh twice one. What they have liked
    or bought already is left out. Empty for a guest and for a visitor with
    no likes.
    """
    if not getattr(user, 'is_authenticated', False):
        return {}
    found = cache.get(_key(user))
    if found is None:
        # Imported here: `product` takes no startup import on `cart`.
        from cart.models import CartItem

        liked = ProductLike.objects.filter(user=user).values('product_id')
        bought = (CartItem.objects
                  .filter(cart__order__user=user, cart__order__status__in=BOUGHT)
                  .values('variant__product_id'))
        through = Product.tags.through
        found = dict(
            through.objects
            .filter(tag__products__likes__user=user)
            .exclude(product_id__in=liked)
            .exclude(product_id__in=bought)
            .values('product_id')
            .annotate(score=Count('pk'))
            .values_list('product_id', 'score')
        )
        cache.set(_key(user), found, TTL)
    return found


def forget(user):
    """Drop a visitor's scores, so their next page reflects a like just made."""
    cache.delete(_key(user))


def order(qs, user, then):
    """``qs`` in "Siz uchun" order for ``user``, and whether it is theirs.

    ``then`` is the order to fall back on and to break ties with: the shop's
    most-liked order. Returns ``(queryset, personal)``; ``personal`` is false
    when there was nothing to go by and the list is the most-liked one.
    """
    found = scores(user)
    if not found:
        return qs.order_by(*then), False
    score = Case(*[When(pk=pk, then=Value(n)) for pk, n in found.items()],
                 default=Value(0), output_field=IntegerField())
    return qs.annotate(rec_score=score).order_by('-rec_score', *then), True


def similar(product, then, limit=4):
    """Ids of the designs most like ``product``, the most alike first.

    By shared tags; where fewer than ``limit`` share any, the same category
    fills the strip, then the most liked, so it is empty only when the shop
    has nothing else on sale.
    """
    on_sale = Exists(Variant.objects.filter(product=OuterRef('pk'), available=True))
    live = Product.objects.filter(on_sale, is_active=True).exclude(pk=product.pk)
    tags = list(product.tags.values_list('pk', flat=True))
    ids = []
    if tags:
        ids = list(live.filter(tags__in=tags)
                   .annotate(shared=Count('tags', distinct=True))
                   .order_by('-shared', *then)
                   .values_list('pk', flat=True)[:limit])
    if len(ids) < limit:
        same = Case(When(category_id=product.category_id, then=Value(0)),
                    default=Value(1), output_field=IntegerField())
        ids += list(live.exclude(pk__in=ids).annotate(other=same)
                    .order_by('other', *then)
                    .values_list('pk', flat=True)[:limit - len(ids)])
    return ids


def _bump(row, field):
    """Add one to today's count of ``field`` for ``row``."""
    if row not in ROWS:
        return
    today = timezone.localdate()
    step = {field: F(field) + 1}
    if RowStat.objects.filter(day=today, row=row).update(**step):
        return
    try:
        with transaction.atomic():
            RowStat.objects.create(day=today, row=row, **{field: 1})
    except IntegrityError:
        # Another request made today's row between the two statements.
        RowStat.objects.filter(day=today, row=row).update(**step)


def shown(row):
    """A signed-in visitor was shown ``row``."""
    _bump(row, 'shown')


def clicked(row):
    """A signed-in visitor opened a design from ``row``."""
    _bump(row, 'clicked')
