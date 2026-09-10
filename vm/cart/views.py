"""Cart views: view the cart, add a variant, update quantity, remove a line."""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
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


@login_required
def cart(request):
    """Show the active cart with per-line totals and a subtotal."""
    cart = services.get_active_cart(request.user)
    items = _annotate_lines(
        cart.cart_items.select_related('variant__product', 'variant__size', 'variant__colour')
        .prefetch_related('variant__product__images')
    )
    subtotal = sum((it.line_total for it in items), Decimal('0'))
    total = subtotal
    return render(request, 'cart/cart.html', {
        'items': items,
        'subtotal': subtotal,
        'total': total,
    })


@require_POST
def cart_add(request, product_id):
    """Add a product variant to the cart; anonymous users are sent to login first."""
    if not request.user.is_authenticated:
        item_url = reverse('item', kwargs={'pk': product_id})
        return redirect(f"{reverse('login')}?next={item_url}")

    product = get_object_or_404(Product, pk=product_id)
    colour_id = request.POST.get('colour') or None
    size_id = request.POST.get('size') or None
    qty = _parse_qty(request.POST.get('quantity', 1))

    # Both calls can fail on stock: resolve_variant if the size has run out,
    # add_variant if it ran out between the page load and the POST.
    try:
        variant = services.resolve_variant(product, colour_id, size_id)
        cart = services.get_active_cart(request.user)
        services.add_variant(cart, variant, qty)
    except services.CartError as e:
        messages.error(request, str(e))
        return redirect('item', pk=product_id)

    messages.success(request, f"{product.name} savatga qo\'shildi.")
    return redirect('shop')


@login_required
@require_POST
def cart_update(request, item_id):
    """Update a line's quantity (a quantity of 0 removes it)."""
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    qty = _parse_qty(request.POST.get('quantity', 1), default=1, lo=0, hi=99)
    try:
        services.set_item_quantity(item, qty)
    except services.CartError as e:
        messages.error(request, str(e))
    return redirect('cart')


@login_required
@require_POST
def cart_remove(request, item_id):
    """Remove a line from the cart."""
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, "Olib tashlandi.")
    return redirect('cart')
