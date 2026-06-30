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

    Raises :class:`CartError` if the selection is ambiguous or invalid, or if the
    matched variant isn't available for sale.
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
    return variant


def add_variant(cart, variant, qty):
    """Add ``qty`` of ``variant`` to the cart, or bump an existing line (capped at 99)."""
    item, created = CartItem.objects.get_or_create(
        cart=cart, variant=variant,
        defaults={'quantity': qty, 'price_stat': variant.price},
    )
    if not created:
        CartItem.objects.filter(pk=item.pk).update(
            quantity=Least(F('quantity') + qty, Value(99))
        )
    return item


def set_item_quantity(item, qty):
    """Set a line's quantity, deleting the line when ``qty`` drops to 0 or below."""
    if qty <= 0:
        item.delete()
    else:
        item.quantity = qty
        item.save(update_fields=['quantity'])
