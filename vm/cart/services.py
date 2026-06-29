"""
Cart domain logic, kept out of the views.

Views handle request parsing, messages, and redirects; the cart rules (resolving
a variant, the lost-update-safe quantity math, opening a cart) live here.
"""
from django.db.models import F, Value
from django.db.models.functions import Least

from .models import Cart, CartItem


class CartError(Exception):
    """Invalid add-to-cart request; the message is user-facing (Uzbek)."""


def get_active_cart(user):
    """Return the user's open cart, creating one if needed."""
    cart, _ = Cart.objects.get_or_create(user=user, status=True)
    return cart


def resolve_variant(product, colour_id, size_id):
    """
    Pin a request down to EXACTLY ONE available variant, or raise CartError.

    Never falls back to "first variant": a POST that omits colour/size (or sends
    a combination that doesn't exist) must fail loudly rather than silently
    adding a variant the user never selected.
    """
    variant_qs = product.variants.all()
    if colour_id:
        variant_qs = variant_qs.filter(colour_id=colour_id)
    if size_id:
        variant_qs = variant_qs.filter(size_id=size_id)

    matches = list(variant_qs[:2])
    if len(matches) != 1:
        # 0 matches  -> invalid / nonexistent combination
        # 2+ matches -> ambiguous: required colour/size not supplied
        raise CartError("Tovar noto'g'ri tanlangan")
    variant = matches[0]

    if not variant.available:
        raise CartError("Ushbu tovar sotuvda yo'q")
    return variant


def add_variant(cart, variant, qty):
    """Add qty of a variant to the cart (capped at 99), lost-update-safe."""
    item, created = CartItem.objects.get_or_create(
        cart=cart, variant=variant,
        defaults={'quantity': qty, 'price_stat': variant.price},
    )
    if not created:
        # Atomic, lost-update-safe increment performed entirely in the DB,
        # capped at 99 via SQL LEAST. Two concurrent adds can't clobber each
        # other the way a Python read-modify-write would.
        # Price snapshot (price_stat) intentionally stays as the original.
        CartItem.objects.filter(pk=item.pk).update(
            quantity=Least(F('quantity') + qty, Value(99))
        )
    return item


def set_item_quantity(item, qty):
    """Set a line's quantity; deletes the line when qty <= 0."""
    if qty <= 0:
        item.delete()
    else:
        item.quantity = qty
        item.save(update_fields=['quantity'])
