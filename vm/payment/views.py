"""Checkout, Click payment start/webhook, and order views."""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.views.decorators.http import require_POST
from click_up.views import ClickWebhook

from .models import Order
from user.models import phone_regex
from . import services


# ---------- presentation helper ----------

def _annotate_lines(items):
    """Attach a ``line_total`` (price_stat * quantity) to each line for templates."""
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out

# ---------- checkout: cart → order ----------

@login_required
def checkout(request):
    """Collect delivery details, validate them, and turn the cart into an Order."""
    cart = services.get_open_cart(request.user)
    if not cart or not cart.cart_items.exists():
        messages.error(request, "Savat bo'sh.")
        return redirect('cart')

    items_qs = (
        cart.cart_items
        .select_related('variant__product', 'variant__size', 'variant__colour')
        .prefetch_related('variant__product__images')
    )
    items = _annotate_lines(items_qs)
    subtotal = sum((it.line_total for it in items), Decimal('0'))
    delivery = Decimal('0')
    total = subtotal + delivery

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        notes = request.POST.get('notes', '').strip()
        payment_method = request.POST.get('payment_method', '').strip()
        if payment_method not in Order.PaymentMethod.values:
            payment_method = Order.PaymentMethod.CLICK

        if not name or not phone or not address:
            messages.error(request, "Ma'lumot va manzilni to'ldiring.")
            return render(request, 'payment/checkout.html', {
                'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
                'form_data': {'name': name, 'phone': phone, 'address': address,
                              'notes': notes, 'payment_method': payment_method},
            })

        try:
            phone_regex(phone)
        except ValidationError as e:
            messages.error(request, e.messages[0])
            return render(request, 'payment/checkout.html', {
                'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
                'form_data': {'name': name, 'phone': phone, 'address': address,
                              'notes': notes, 'payment_method': payment_method},
            })

        try:
            order = services.create_order_from_cart(
                request.user, cart,
                phone=phone, address=address, notes=notes,
                payment_method=payment_method, delivery=delivery,
            )
        except services.CartAlreadyCheckedOut as e:
            messages.info(request, "Buyurtma allaqachon rasmiylashtirilgan.")
            return redirect('payment', order_id=e.existing_order.id)
        except services.EmptyCart:
            messages.error(request, "Savat bo'sh.")
            return redirect('cart')

        messages.success(request, f"Buyurtma qabul qilindi. To'lovni amalga oshiring.")
        return redirect('payment', order_id=order.id)

    return render(request, 'payment/checkout.html', {
        'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
    })


# ---------- payment (Click) ----------

@login_required
def payment(request, order_id):
    """Show the payment page for an order."""
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product'),
        pk=order_id, user=request.user,
    )
    return render(request, 'payment/payment.html', {'order': order})


@login_required
@require_POST
def payment_start(request, order_id):
    """Generate a Click pay link and redirect to it (only while still PAYING)."""
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.status != Order.Status.PAYING:
        messages.info(request, "Bu buyurtma uchun to'lov holati allaqachon o'zgargan.")
        return redirect('order_status', pk=order.id)

    return_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
    paylink = services.generate_click_paylink(order, return_url)
    return redirect(paylink)


class ClickWebhookAPIView(ClickWebhook):
    """Single Click callback endpoint; click_up routes Prepare/Complete internally."""
    def successfully_payment(self, params):
        services.apply_successful_payment(params.click_trans_id)

    def cancelled_payment(self, params):
        services.apply_cancelled_payment(params.click_trans_id)


# ---------- viewing an order ----------

@login_required
def order_detail(request, pk):
    """Order detail page, with per-line totals computed for the template."""
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product__images'),
        pk=pk, user=request.user,
    )
    for it in order.cart.cart_items.all():
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
    return render(request, 'payment/order_detail.html', {'order': order})


@login_required
def order_status(request, pk):
    """Lightweight order-status page (used for post-payment status checks)."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, 'payment/status.html', {'order': order})


# ---------- cancel ----------

@login_required
@require_POST
def order_cancel(request, pk):
    """Cancel an order that is still awaiting payment."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if services.cancel_order(order):
        messages.success(request, f"#{order.id} bekor qilindi.")
    else:
        messages.error(request, "Buyurtmani bekor qilib bo'lmadi.")
    return redirect('order_status', pk=order.id)
