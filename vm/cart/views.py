from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Cart, CartItem
from product.models import Product, Variant


def _get_active_cart(user):
    """Return the user's open cart, creating one if needed."""
    cart, _ = Cart.objects.get_or_create(user=user, status=True)
    return cart


def _annotate_lines(items):
    """Attach line_total to each cart item for the template."""
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out


@login_required
def cart(request):
    cart = _get_active_cart(request.user)
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


@login_required
@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    colour_id = request.POST.get('colour') or None
    size_id = request.POST.get('size') or None
    qty = max(1, int(request.POST.get('quantity', 1) or 1))

    # Resolve variant
    variant_qs = product.variants.all()
    if colour_id:
        variant_qs = variant_qs.filter(colour_id=colour_id)
    if size_id:
        variant_qs = variant_qs.filter(size_id=size_id)
    variant = variant_qs.first()

    if not variant:
        messages.error(request, "Tovar noto'g'ri tanlangan")
        return redirect('item', pk=product_id)

    if not variant.available:
        messages.error(request, "Ushbu tovar sotuvda yo'q")
        return redirect('item', pk=product_id)

    cart = _get_active_cart(request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart, variant=variant,
        defaults={'quantity': qty, 'price_stat': variant.price},
    )
    if not created:
        item.quantity = min(99, item.quantity + qty)
        # snapshot price stays as original for that line
        item.save(update_fields=['quantity'])

    messages.success(request, f"{product.name} savatga qo\'shildi.")
    return redirect('shop')


@login_required
@require_POST
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    qty = int(request.POST.get('quantity', 1) or 1)
    if qty <= 0:
        item.delete()
    else:
        item.quantity = min(99, qty)
        item.save(update_fields=['quantity'])
    return redirect('cart')


@login_required
@require_POST
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, "Olib tashlandi.")
    return redirect('cart')
