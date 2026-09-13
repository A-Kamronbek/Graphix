"""Cart views: view the cart, add a variant, update quantity, remove a line.

None of these require an account. A guest fills a cart against their session and
the login wall sits at checkout instead, which is where it belongs: asking
someone to register before they can even see a price is the biggest drop-off
point a small shop has (§17 #24). Ownership is still enforced on every line —
a cart belongs either to a user or to a session, and a line is only reachable
through the cart the request actually owns.
"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import Http404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .models import CartItem
from product.models import Product
from . import services


def _parse_qty(raw, default=1, lo=1, hi=99):
    """Parse a quantity from raw input and clamp it into [lo, hi]."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _annotate_lines(items):
    """Attach a ``line_total`` (price_stat * quantity) to each item for templates."""
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out


def _own_line(request, item_id):
    """Return a line of the requester's own cart, or 404.

    The cart is resolved first and the line is looked up *inside* it, so the
    check is the same one for a signed-in customer and for a guest: there is no
    branch where a missing user silently widens the query.
    """
    cart = services.find_cart(request)
    if cart is None:
        raise Http404('no open cart')
    return get_object_or_404(CartItem, pk=item_id, cart=cart)


def cart(request):
    """Show the active cart with per-line totals and a subtotal."""
    cart = services.find_cart(request)
    items = _annotate_lines(
        cart.cart_items.select_related('variant__product', 'variant__size', 'variant__colour')
        .prefetch_related('variant__product__images')
    ) if cart else []
    subtotal = sum((it.line_total for it in items), Decimal('0'))
    total = subtotal
    return render(request, 'cart/cart.html', {
        'items': items,
        'subtotal': subtotal,
        'total': total,
    })


@require_POST
def cart_add(request, product_id):
    """Add a product variant to the cart. No account needed."""
    product = get_object_or_404(Product, pk=product_id)

    colour_id = request.POST.get('colour') or None
    size_id = request.POST.get('size') or None
    qty = _parse_qty(request.POST.get('quantity', 1))

    # Both calls can fail on stock: resolve_variant if the size has run out,
    # add_variant if it ran out between the page load and the POST.
    try:
        variant = services.resolve_variant(product, colour_id, size_id)
        cart = services.get_active_cart(request)
        services.add_variant(cart, variant, qty)
    except services.CartError as e:
        messages.error(request, str(e))
        return redirect('item', slug=product.slug)

    messages.success(request, _("%(name)s savatga qoʻshildi.")
                      % {'name': product.name})
    return redirect('shop')


@require_POST
def cart_update(request, item_id):
    """Update a line's quantity (a quantity of 0 removes it)."""
    item = _own_line(request, item_id)
    qty = _parse_qty(request.POST.get('quantity', 1), default=1, lo=0, hi=99)
    try:
        services.set_item_quantity(item, qty)
    except services.CartError as e:
        messages.error(request, str(e))
    return redirect('cart')


@require_POST
def cart_remove(request, item_id):
    """Remove a line from the cart."""
    item = _own_line(request, item_id)
    item.delete()
    messages.success(request, _("Olib tashlandi."))
    return redirect('cart')
