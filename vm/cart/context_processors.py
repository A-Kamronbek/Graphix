"""Counts the header badges read. One cheap aggregate each, on every page."""
from django.db.models import Sum

from .models import Cart


def cart_count(request):
    """Total units in the visitor's open cart, for the nav badge.

    Works for a guest too: their cart is keyed to the session. The lookup is
    read-only — it never creates a session or a cart, so a crawler hitting every
    page leaves nothing behind (see ``services.find_cart``).
    """
    if request.user.is_authenticated:
        carts = Cart.objects.filter(user=request.user, status=True)
    else:
        key = request.session.session_key
        if not key:
            return {'cart_count': 0}
        carts = Cart.objects.filter(session_key=key, user__isnull=True, status=True)
    total = carts.aggregate(n=Sum('cart_items__quantity'))['n']
    return {'cart_count': total or 0}


def liked_count(request):
    """How many products the visitor has hearted, for the nav badge.

    Anonymous visitors have no saved list — the heart asks them to sign in —
    so this is 0 without a query. Imported lazily so the cart app does not take
    a hard import on the product app at startup.
    """
    if not request.user.is_authenticated:
        return {'liked_count': 0}
    from product.models import ProductLike
    return {'liked_count': ProductLike.objects.filter(user=request.user).count()}
