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
    """Safely parse a quantity from request data, clamped to [lo, hi].
    Non-numeric input falls back to `default` instead of raising."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _annotate_lines(items):
    """Attach line_total to each cart item for the template."""
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out


@login_required
def cart(request):
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
    # Guests: send them to login, then back to the PRODUCT PAGE (a GET URL).
    # This endpoint is POST-only, so it must never become the post-login `next`:
    # a GET redirect to it 405s, and a back-button retry then fails CSRF because
    # login() rotates the token. Returning to the item page avoids all of that.
    if not request.user.is_authenticated:
        item_url = reverse('item', kwargs={'pk': product_id})
        return redirect(f"{reverse('login')}?next={item_url}")

    product = get_object_or_404(Product, pk=product_id)
    colour_id = request.POST.get('colour') or None
    size_id = request.POST.get('size') or None
    qty = _parse_qty(request.POST.get('quantity', 1))

    try:
        variant = services.resolve_variant(product, colour_id, size_id)
    except services.CartError as e:
        messages.error(request, str(e))
        return redirect('item', pk=product_id)

    cart = services.get_active_cart(request.user)
    services.add_variant(cart, variant, qty)

    messages.success(request, f"{product.name} savatga qo\'shildi.")
    return redirect('shop')


@login_required
@require_POST
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    qty = _parse_qty(request.POST.get('quantity', 1), default=1, lo=0, hi=99)
    services.set_item_quantity(item, qty)
    return redirect('cart')


@login_required
@require_POST
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, "Olib tashlandi.")
    return redirect('cart')
