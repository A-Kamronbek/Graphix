"""Cart operations: resolve the active cart, match a variant, add/update items."""
from django.db.models import F, Value
from django.db.models.functions import Least

from .models import Cart, CartItem


class CartError(Exception):
    """Raised when a cart operation can't proceed (bad selection or unavailable item)."""

def get_active_cart(user):
    """Return the user's open cart, creating one if none exists."""
    cart, _ = Cart.objects.get_or_create(user=user, status=True)
    return cart


def resolve_variant(product, colour_id, size_id):
    """Resolve the single variant matching the chosen colour/size.

    Raises :class:`CartError` if the selection is ambiguous or invalid, if the
    matched variant isn't for sale, or if it has run out. ``available`` is the
    owner's switch and ``stock`` is the count; both have to agree, so they get
    separate messages — "sold out" and "not for sale" mean different things to a
    customer.
    """
    variant_qs = product.variants.all()
    if colour_id:
        variant_qs = variant_qs.filter(colour_id=colour_id)
    if size_id:
        variant_qs = variant_qs.filter(size_id=size_id)

    matches = list(variant_qs[:2])
    if len(matches) != 1:
        raise CartError("Tovar noto'g'ri tanlangan")
    variant = matches[0]

    if not variant.available:
        raise CartError("Ushbu tovar sotuvda yo'q")
    if variant.stock <= 0:
        raise CartError("Ushbu o'lcham tugagan")
    return variant


def variant_cap(variant):
    """Return the most units of ``variant`` one cart line may hold.

    The 99 ceiling is a sanity limit on the quantity widget; ``stock`` is the
    real one. Whichever is lower wins.
    """
    return min(99, variant.stock)


def add_variant(cart, variant, qty):
    """Add ``qty`` of ``variant`` to the cart, or bump an existing line.

    Capped at ``min(99, stock)``. The bump is done with a single ``UPDATE`` using
    ``Least(F('quantity') + qty, cap)`` rather than a Python read-modify-write, so
    two tabs adding the same item can't race past the cap. ``Least`` also pulls an
    existing line back down if stock has fallen below it since it was added.
    """
    cap = variant_cap(variant)
    if cap <= 0:
        raise CartError("Ushbu o'lcham tugagan")

    item, created = CartItem.objects.get_or_create(
        cart=cart, variant=variant,
        defaults={'quantity': min(qty, cap), 'price_stat': variant.price},
    )
    if not created:
        CartItem.objects.filter(pk=item.pk).update(
            quantity=Least(F('quantity') + qty, Value(cap))
        )
    return item


def set_item_quantity(item, qty):
    """Set a line's quantity, deleting the line when ``qty`` drops to 0 or below.

    Clamped to what is actually in stock, so a hand-edited quantity field can't
    over-order.
    """
    if qty <= 0:
        item.delete()
        return

    cap = variant_cap(item.variant)
    if cap <= 0:
        item.delete()
        raise CartError("Ushbu o'lcham tugagan")

    item.quantity = min(qty, cap)
    item.save(update_fields=['quantity'])
