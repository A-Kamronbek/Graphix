import random
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import LoginForm, SignupForm, OTPForm
from payment.models import Order


OTP_TTL_SECONDS = 5 * 60          # 5 minutes — absolute, not reset by resend
OTP_RESEND_COOLDOWN = 60          # 60 seconds between resends


def _generate_otp(request, reset_expiry):
    """
    Create a fresh 6-digit code.
    - reset_expiry=True  -> start a brand new 5-minute window (used on signup)
    - reset_expiry=False -> keep the existing absolute expiry (used on resend)
    """
    code = f"{random.randint(0, 999999):06d}"
    if reset_expiry or 'otp_expires_at' not in request.session:
        expires_at = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
        request.session['otp_expires_at'] = expires_at.isoformat()
    request.session['otp_code'] = code
    request.session['otp_last_sent_at'] = timezone.now().isoformat()
    # TODO: replace with real SMS gateway. For dev, log it.
    print(f"[OTP] code for user {request.user} -> {code}")
    return code


def _otp_expired(request):
    raw = request.session.get('otp_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def _ttl_remaining(request):
    raw = request.session.get('otp_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def _resend_cooldown(request):
    raw = request.session.get('otp_last_sent_at')
    if not raw:
        return 0
    try:
        last = timezone.datetime.fromisoformat(raw)
        elapsed = (timezone.now() - last).total_seconds()
        return max(0, int(OTP_RESEND_COOLDOWN - elapsed))
    except ValueError:
        return 0


def _cancel_and_delete(request):
    """
    Wipe the unverified user, clear session, log out. Returns a redirect to signup.
    Refuses to delete a verified user as a safety guard.
    """
    user = request.user
    if user.is_authenticated and not user.phone_verified:
        logout(request)  # flushes session (incl. otp_* keys)
        try:
            user.delete()
        except Exception:
            pass
    return redirect('signup')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('account')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Hush kelibsiz!.")
        return redirect(request.GET.get('next') or 'shop')
    return render(request, 'user/login.html', {'form': form})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('account')
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        _generate_otp(request, reset_expiry=True)
        return redirect('verify_phone')
    return render(request, 'user/signup.html', {'form': form})


@login_required
def verify_phone(request):
    if request.user.phone_verified:
        return redirect('account')

    # If somehow there's no OTP state yet (e.g. came in via a stale session), seed one.
    if 'otp_code' not in request.session:
        _generate_otp(request, reset_expiry=True)

    form = OTPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if _otp_expired(request):
            messages.error(request, "Kod muddati tugagan. Qaytadan ro'yxatdan o'ting.")
            return _cancel_and_delete(request)

        submitted = form.cleaned_data['code']
        if submitted != request.session.get('otp_code'):
            form.add_error('code', "Kod noto'g'ri.")
        else:
            request.user.phone_verified = True
            request.user.save(update_fields=['phone_verified'])
            for k in ('otp_code', 'otp_expires_at', 'otp_last_sent_at'):
                request.session.pop(k, None)
            messages.success(request, "Telefon raqam tasdiqlandi.")
            return redirect('account')

    return render(request, 'user/verify_phone.html', {
        'form': form,
        'phone': request.user.phone,
        'resend_in': _resend_cooldown(request),
        'ttl': _ttl_remaining(request),
    })


@login_required
@require_POST
def resend_otp(request):
    if request.user.phone_verified:
        return redirect('account')

    # Hard expiry — even resends can't revive a dead session.
    if _otp_expired(request):
        messages.error(request, "Vaqt tugadi. Qaytadan ro'yxatdan o'ting.")
        return _cancel_and_delete(request)

    if _resend_cooldown(request) > 0:
        messages.error(request, "Iltimos biroz kuting.")
        return redirect('verify_phone')

    _generate_otp(request, reset_expiry=False)
    messages.success(request, "Yangi kod yuborildi.")
    return redirect('verify_phone')


@login_required
@require_POST
def cancel_verification(request):
    messages.info(request, "Ro'yxatdan o'tish bekor qilindi.")
    return _cancel_and_delete(request)


@login_required
@require_POST
def expire_verification(request):
    """Triggered by the client when the OTP timer hits 0.
    Delete the unverified user and send them to home as a guest."""
    user = request.user
    if user.is_authenticated and not user.phone_verified:
        logout(request)
        try:
            user.delete()
        except Exception:
            pass
    return redirect('home')


@login_required
def account(request):
    recent_orders = Order.objects.filter(user=request.user).select_related('cart')[:5]
    return render(request, 'user/account.html', {
        'recent_orders': recent_orders,
    })


@login_required
def account_orders(request):
    orders = Order.objects.filter(user=request.user).select_related('cart').prefetch_related('cart__cart_items')
    return render(request, 'user/account_orders.html', {'orders': orders})
