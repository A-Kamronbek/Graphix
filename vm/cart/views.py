from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import F, Value
from django.db.models.functions import Least
from .models import Cart, CartItem
from product.models import Product, Variant


def _parse_qty(raw, default=1, lo=1, hi=99):
    """Safely parse a quantity from request data, clamped to [lo, hi].
    Non-numeric input falls back to `default` instead of raising."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


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
    qty = _parse_qty(request.POST.get('quantity', 1))

    # Resolve variant — must pin down to EXACTLY ONE variant.
    # Never fall back to "first variant": a POST that omits colour/size (or
    # sends a combination that doesn't exist) must fail loudly rather than
    # silently adding a variant the user never selected.
    variant_qs = product.variants.all()
    if colour_id:
        variant_qs = variant_qs.filter(colour_id=colour_id)
    if size_id:
        variant_qs = variant_qs.filter(size_id=size_id)

    matches = list(variant_qs[:2])
    if len(matches) != 1:
        # 0 matches  -> invalid / nonexistent combination
        # 2+ matches -> ambiguous: required colour/size not supplied
        messages.error(request, "Tovar noto'g'ri tanlangan")
        return redirect('item', pk=product_id)
    variant = matches[0]

    if not variant.available:
        messages.error(request, "Ushbu tovar sotuvda yo'q")
        return redirect('item', pk=product_id)

    cart = _get_active_cart(request.user)
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

    messages.success(request, f"{product.name} savatga qo\'shildi.")
    return redirect('shop')


@login_required
@require_POST
def cart_update(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    qty = _parse_qty(request.POST.get('quantity', 1), default=1, lo=0, hi=99)
    if qty <= 0:
        item.delete()
    else:
        item.quantity = qty
        item.save(update_fields=['quantity'])
    return redirect('cart')


@login_required
@require_POST
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    messages.success(request, "Olib tashlandi.")
    return redirect('cart')
