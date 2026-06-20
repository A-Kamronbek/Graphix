from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.db import transaction

from cart.models import Cart
from .models import Order
from user.models import phone_regex


# ---------- helpers ----------

def _get_open_cart(user):
    """Return the user's currently open cart, or None."""
    return Cart.objects.filter(user=user, status=True).first()


def _annotate_lines(items):
    out = []
    for it in items:
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
        out.append(it)
    return out


# ---------- checkout: cart → order ----------

@login_required
def checkout(request):
    cart = _get_open_cart(request.user)
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
        # Only accept a known method; anything else (or missing) falls back to Click,
        # which is currently the only enabled option.
        if payment_method not in Order.PaymentMethod.values:
            payment_method = Order.PaymentMethod.CLICK

        # required fields
        if not name or not phone or not address:
            messages.error(request, "Ma'lumot va manzilni to'ldiring.")
            return render(request, 'payment/checkout.html', {
                'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
                'form_data': {'name': name, 'phone': phone, 'address': address,
                              'notes': notes, 'payment_method': payment_method},
            })

        # phone format (same validator as User.phone)
        try:
            phone_regex(phone)
        except ValidationError as e:
            messages.error(request, e.messages[0])
            return render(request, 'payment/checkout.html', {
                'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
                'form_data': {'name': name, 'phone': phone, 'address': address,
                              'notes': notes, 'payment_method': payment_method},
            })

        # Create the order atomically and close the cart so a fresh one is opened next time.
        with transaction.atomic():
            # Lock the cart row. A second, near-simultaneous checkout on the same
            # cart (e.g. a double-click) blocks here until the first transaction
            # commits, then re-reads the now-closed status below — instead of both
            # racing to Order.objects.create() and the second hitting an
            # IntegrityError on the OneToOne cart field (a 500 for the user).
            locked_cart = (
                Cart.objects.select_for_update()
                .filter(pk=cart.pk, user=request.user)
                .first()
            )

            # Already checked out by the concurrent request -> don't create a
            # second Order. Send the user to the order that already exists.
            if locked_cart is None or not locked_cart.status:
                existing = Order.objects.filter(cart_id=cart.pk).first()
                if existing:
                    messages.info(request, "Buyurtma allaqachon rasmiylashtirilgan.")
                    return redirect('payment', order_id=existing.id)
                messages.error(request, "Savat bo'sh.")
                return redirect('cart')

            order = Order.objects.create(
                user=request.user,
                cart=locked_cart,
                phone=phone,
                address=address,
                notes=notes,
                payment_method=payment_method,
                total_price=total,
                status=Order.Status.PAYING,  # straight to "awaiting payment"
            )
            locked_cart.status = False
            locked_cart.save(update_fields=['status'])

        messages.success(request, f"Buyurtma qabul qilindi. To'lovni amalga oshiring.")
        return redirect('payment', order_id=order.id)

    return render(request, 'payment/checkout.html', {
        'items': items, 'subtotal': subtotal, 'delivery': delivery, 'total': total,
    })


# ---------- payment (Click stub) ----------

@login_required
def payment(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product'),
        pk=order_id, user=request.user,
    )
    return render(request, 'payment/payment.html', {'order': order})


@login_required
@require_POST
def payment_start(request, order_id):
    """
    TODO — Click integration goes here.

    Typical flow with Click:
      1. Build a payment request payload (merchant_id, service_id, amount, transaction_param)
      2. Create a PENDING transaction record in your DB (link it to this Order)
      3. Redirect the user to Click's hosted page, e.g.
            https://my.click.uz/services/pay?...
      4. Implement Prepare / Complete callback endpoints that Click will hit server-to-server
         to confirm the payment, and on success update Order.status = Order.Status.PAID.

    For now this is a stub — it just bounces back to the payment page.
    """
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    messages.info(request, "Click integration not connected yet — payment endpoint pending.")
    return redirect('payment', order_id=order.id)


# ---------- viewing an order ----------

@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('cart').prefetch_related('cart__cart_items__variant__product__images'),
        pk=pk, user=request.user,
    )
    # annotate line_total
    for it in order.cart.cart_items.all():
        it.line_total = (it.price_stat or Decimal('0')) * it.quantity
    return render(request, 'payment/order_detail.html', {'order': order})


@login_required
def order_status(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, 'payment/status.html', {'order': order})


# ---------- cancel ----------

@login_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status == Order.Status.PAYING:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status'])
        messages.success(request, f"#{order.id} bekor qilindi.")
    else:
        messages.error(request, "Buyurtmani bekor qilib bo'lmadi.")
    return redirect('order_status', pk=order.id)
