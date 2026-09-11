"""Counts the header badges read. One cheap aggregate each, on every page."""
from django.db.models import Sum

from .models import Cart


def cart_count(request):
    """Total units in the visitor's open cart, for the nav badge.

    Anonymous visitors get 0 until Phase 6g gives guests a session-keyed cart.
    """
    if not request.user.is_authenticated:
        return {'cart_count': 0}
    total = (
        Cart.objects.filter(user=request.user, status=True)
        .aggregate(n=Sum('cart_items__quantity'))['n']
    )
    return {'cart_count': total or 0}


def liked_count(request):
    """How many products the visitor has hearted, for the nav badge.

    Reading the count is Phase 5 (the header has to render something); the toggle
    that changes it is Phase 6b. Imported lazily so the cart app does not take a
    hard import on the product app at startup.
    """
    if not request.user.is_authenticated:
        return {'liked_count': 0}
    from product.models import ProductLike
    return {'liked_count': ProductLike.objects.filter(user=request.user).count()}
