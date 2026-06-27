from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db import transaction
from click_up.views import ClickWebhook
from click_up import ClickUp
from django.conf import settings
from click_up.models import ClickTransaction

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

            # Recompute the total from the LOCKED cart's lines. The `total`
            # computed before the lock can be stale: a concurrent cart_add in
            # another tab may have inserted a line between that read and the
            # lock, which would otherwise persist an undercounted order.
            locked_lines = locked_cart.cart_items.all()
            if not locked_lines:
                messages.error(request, "Savat bo'sh.")
                return redirect('cart')
            locked_total = sum(
                ((it.price_stat or Decimal('0')) * it.quantity for it in locked_lines),
                Decimal('0'),
            ) + delivery

            order = Order.objects.create(
                user=request.user,
                cart=locked_cart,
                phone=phone,
                address=address,
                notes=notes,
                payment_method=payment_method,
                total_price=locked_total,
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
    """Generate a Click pay link for this order and
    redirect the user to it."""
    
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    # Don't start a new payment for an order that's no longer awaiting one.
    if order.status != Order.Status.PAYING:
        messages.info(request, "Bu buyurtma uchun to'lov holati allaqachon o'zgargan.")
        return redirect('order_status', pk=order.id)

    click_up = ClickUp(service_id=settings.CLICK_SERVICE_ID,
                       merchant_id=settings.CLICK_MERCHANT_ID)
    return_url = request.build_absolute_uri(reverse('order_detail', args=[order.id]))
    paylink = click_up.initializer.generate_pay_link(
        id=order.id,
        amount=order.total_price,
        return_url=return_url,
    )
    return redirect(paylink)


class ClickWebhookAPIView(ClickWebhook):
    """
    Click calls this server-to-server (Prepare + Complete). The library verifies
    the signature, checks the amount against CLICK_AMOUNT_FIELD, and records a
    ClickTransaction. We only need to move the Order's status in the callbacks.
    `params.merchant_trans_id` is the order id we passed as `id` to the pay link.
    """
    def successfully_payment(self, params):
        """Click confirmed the payment -> mark the order PAID."""
        transaction = ClickTransaction.objects.get(
            transaction_id=params.Click_trans_id
        )
        order = Order.objects.get(id=transaction.account_id)
        if order.status != Order.Status.PAID:
            order.status = Order.Status.PAID
            order.save(update_fields=['status', 'updated_at'])

    def cancelled_payment(self, params):
        """Click reported a cancelled/failed payment -> mark the order CANCELLED
        (but never override an order that already completed)."""
        transaction = ClickTransaction.objects.get(
            transaction_id=params.Click_trans_id
        )
        if transaction.state == ClickTransaction.CANCELLED:
            order = Order.objects.get(id=transaction.account_id)
            if order.status not in (Order.Status.PAID, Order.Status.CANCELLED):
                order.status = Order.Status.CANCELLED
                order.save(update_fields=['status', 'updated_at'])


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
