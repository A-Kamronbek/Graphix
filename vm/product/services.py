"""Catalogue operations that change data: the heart, and review moderation.

Each of these changes two things that must agree — a row and a denormalised
count on the product — so both happen together or not at all, which is why
they live in services rather than in a view or an admin action.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Avg, Count, F
from django.utils import timezone

from .models import Product, ProductLike, Review, ReviewImage


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



# ------------------------------------------------------------------ reviews

def recompute_rating(product_id):
    """Rewrite ``rating_avg`` and ``review_count`` from the approved reviews.

    Recomputed from the rows rather than adjusted by a delta, because the
    inputs change in too many ways to keep a running total honest: a review is
    approved, then rejected, then approved again; a customer's account is
    deleted and takes their reviews with it; the owner edits a rating in the
    admin. A recount is one cheap aggregate over a handful of rows, and it is
    correct after any of those without knowing which one happened.

    **Approved reviews only.** A pending review must not move the public number
    before a human has looked at it, which is the whole point of moderation
    (§17 #25). A product whose last approved review is rejected goes back to
    0 / 0, and the product page then hides the rating block entirely rather
    than showing nobody a zero.
    """
    stats = (Review.objects
             .filter(product_id=product_id, status=Review.Status.APPROVED)
             .aggregate(avg=Avg('rating'), n=Count('id')))
    count = stats['n'] or 0
    # One decimal, matching the column: 4.25 stars is false precision, and the
    # field is DecimalField(max_digits=2, decimal_places=1).
    # Through Decimal and ROUND_HALF_UP rather than `round()`. `Avg` hands
    # back a float, and Python's round() is round-half-to-EVEN: four ratings
    # of 4, 4, 5, 4 average 4.25 and came out as 4.2, while 4.35 would come
    # out as 4.4. Nobody reading a star rating expects the direction to
    # depend on the neighbouring digit, and a value bound for a Decimal
    # column should not be rounded as a float on the way.
    average = (Decimal(str(stats['avg'])).quantize(Decimal('0.1'), ROUND_HALF_UP)
               if count else Decimal('0.0'))
    Product.objects.filter(pk=product_id).update(rating_avg=average, review_count=count)
    return average, count


@transaction.atomic
def moderate(queryset, status, by=None):
    """Set ``status`` on every review in ``queryset`` and fix the ratings.

    A bulk ``update()`` is deliberate — moderating fifty reviews should be one
    statement — but it skips ``save()`` and therefore every signal, so the
    recompute has to be driven from here. The affected product ids are read
    *before* the update, because the rows are about to stop matching the
    filter that found them.
    """
    product_ids = list(queryset.values_list('product_id', flat=True).distinct())
    count = queryset.update(status=status, moderated_by=by,
                            moderated_at=timezone.now())
    for product_id in product_ids:
        recompute_rating(product_id)
    return count


class NotEligible(Exception):
    """Raised when the rules below say this person may not review this product."""


def products_in_order(order):
    """The distinct products an order actually contained.

    Read through the cart the order froze, which is where the lines live. A
    product bought twice in two sizes is one product to review.
    """
    seen, out = set(), []
    for line in order.cart.cart_items.select_related('variant__product'):
        product = line.variant.product
        if product.pk not in seen:
            seen.add(product.pk)
            out.append(product)
    return out


def reviewable(user, order):
    """The products in ``order`` that ``user`` may still review, with the
    review they have already left where they have left one.

    Returns a list of ``(product, existing_review_or_None)``, so the page can
    show a form for the ones that are open and the status for the ones that
    are not — a customer who has reviewed something should be told it is with
    the moderators, not shown an empty form that will be refused.
    """
    if order.user_id != user.pk:
        return []
    existing = {r.product_id: r for r in
                Review.objects.filter(user=user,
                                      product__in=products_in_order(order))}
    return [(p, existing.get(p.pk)) for p in products_in_order(order)]


def check_may_review(user, order, product):
    """Raise :class:`NotEligible` unless every rule passes.

    Server-side and in one place, because this is the whole basis of the
    "verified purchase" badge. Four rules, each of which has to hold:

    * the order is **this** customer's — otherwise anyone with an order number
      could review anything;
    * it is **delivered** (`done`). A review written before the parcel arrives
      is a review of the checkout, and a paid-but-unshipped order is exactly
      what someone gaming ratings would use;
    * it **contained this product**;
    * they have **not reviewed it before**, from this order or any other. The
      database says so too, with a unique constraint on (user, product) — this
      check exists to produce a sentence rather than an IntegrityError.
    """
    if order.user_id != user.pk:
        raise NotEligible('not your order')
    if order.status != order.Status.DONE:
        raise NotEligible('order not delivered')
    if not any(p.pk == product.pk for p in products_in_order(order)):
        raise NotEligible('product not in this order')
    if Review.objects.filter(user=user, product=product).exists():
        raise NotEligible('already reviewed')


@transaction.atomic
def create_review(user, order, product, rating, text='', photos=()):
    """Create a pending review with its photos. Eligibility is re-checked here.

    Re-checked rather than assumed: the view checks it too, to decide what to
    render, and a rule enforced only where a page happens to call it is not
    enforced at all.

    The review lands ``pending`` and moves no rating — ``recompute_rating``
    counts approved rows only — so nothing a customer writes reaches the
    product page before a human has read it (§17 #25).
    """
    check_may_review(user, order, product)
    review = Review.objects.create(user=user, order=order, product=product,
                                   rating=rating, text=text.strip())
    for index, photo in enumerate(photos):
        ReviewImage.objects.create(review=review, picture=photo, order=index)
    return review
