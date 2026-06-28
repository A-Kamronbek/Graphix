import random
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    LoginForm, SignupForm, OTPForm, ForgotPasswordForm, ResetPasswordForm,
    ProfileForm, ChangePasswordForm,
)
from .models import User
from payment.models import Order
from core.sms import send_sms
from core.ratelimit import is_rate_limited, is_currently_limited, RATE_LIMIT_MESSAGE


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
    send_sms(request.user.phone,
             f"Vallaymade saytida ro'yhatdan o'tish uchun kodingiz: {code}")
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


def _cancel_and_delete(request, reason=None):
    """
    Wipe the unverified user, clear session, log out. Returns a redirect to signup.
    Refuses to delete a verified user as a safety guard.

    `reason` is passed back as a ?reason= query param (NOT a flash message),
    because logout() flushes the session and would eat any messages.* added here.
    The signup page reads it and shows the matching explanation.
    """
    user = request.user
    if user.is_authenticated and not user.phone_verified:
        logout(request)  # flushes session (incl. otp_* keys)
        try:
            user.delete()
        except Exception:
            pass
    if reason:
        return redirect(f"{reverse('signup')}?reason={reason}")
    return redirect('signup')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('account')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        username = request.POST.get('username', '')
        # Per-account limit stops password brute-force even from rotating IPs;
        # the IP limit is a generous secondary net.
        if (is_rate_limited(request, 'login_user', 8, 300, ident=username)
                or is_rate_limited(request, 'login_ip', 60, 300)):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return render(request, 'user/login.html', {'form': form, 'rate_limited': True})
        elif form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Xush kelibsiz!")
            # Only honor a safe, internal `next`; otherwise fall back to shop.
            nxt = request.GET.get('next') or request.POST.get('next')
            if nxt and url_has_allowed_host_and_scheme(
                nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(nxt)
            return redirect('shop')
    return render(request, 'user/login.html', {
        'form': form,
        'rate_limited': is_currently_limited(request, 'login_ip', 60),
    })


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('account')
    form = SignupForm(request.POST or None)
    limited = is_currently_limited(request, 'signup_ip', 50)
    if request.method == 'POST':
        phone = request.POST.get('phone', '')
        if (is_rate_limited(request, 'signup_ip', 50, 3600)
                or is_rate_limited(request, 'signup_phone', 4, 600, ident=phone)):
            limited = True
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            user = form.save()
            login(request, user)
            _generate_otp(request, reset_expiry=True)
            return redirect('verify_phone')

    # Explanation banner after an OTP flow ended (kept in the URL, not the
    # session, since _cancel_and_delete flushes the session via logout()).
    reason_messages = {
        'expired': "Tasdiqlash kodi muddati tugadi. Iltimos, qaytadan ro'yxatdan o'ting.",
        'cancelled': "Ro'yxatdan o'tish bekor qilindi.",
    }
    notice = reason_messages.get(request.GET.get('reason'))

    return render(request, 'user/signup.html', {'form': form, 'notice': notice, 'rate_limited': limited})


@login_required
def verify_phone(request):
    if request.user.phone_verified:
        return redirect('account')

    # Expired window -> the account is a throwaway from an abandoned signup.
    # Delete it and bounce to signup (covers both GET landings and code submits).
    if 'otp_expires_at' in request.session and _otp_expired(request):
        return _cancel_and_delete(request, reason='expired')

    # Seed a code if there isn't one yet (e.g. existing unverified user logging in).
    if 'otp_code' not in request.session:
        _generate_otp(request, reset_expiry=True)

    form = OTPForm(request.POST or None)
    if request.method == 'POST':
        if is_rate_limited(request, 'otp_verify', 12, 300, ident=f"u{request.user.pk}"):
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            if form.cleaned_data['code'] != request.session.get('otp_code'):
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
        'rate_limited': is_currently_limited(request, 'otp_verify', 12, ident=f"u{request.user.pk}"),
        'resend_limited': is_currently_limited(request, 'otp_resend', 8, ident=f"u{request.user.pk}"),
    })


@login_required
@require_POST
def resend_otp(request):
    if request.user.phone_verified:
        return redirect('account')

    if is_rate_limited(request, 'otp_resend', 8, 600, ident=f"u{request.user.pk}"):
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect('verify_phone')

    # Window expired -> throwaway account from an abandoned signup; delete it.
    if _otp_expired(request):
        return _cancel_and_delete(request, reason='expired')

    if _resend_cooldown(request) > 0:
        messages.error(request, "Iltimos biroz kuting.")
        return redirect('verify_phone')

    _generate_otp(request, reset_expiry=False)
    messages.success(request, "Yangi kod yuborildi.")
    return redirect('verify_phone')


@login_required
@require_POST
def cancel_verification(request):
    return _cancel_and_delete(request, reason='cancelled')


@login_required
@require_POST
def expire_verification(request):
    """
    Hardened expiry endpoint. The client no longer auto-submits here on a
    countdown; this is kept as a server-verified path. It deletes the account
    ONLY if the absolute OTP expiry has genuinely passed according to the SERVER
    clock — so a stray or forged POST (XSS, a browser extension, an ad in another
    tab) can't delete a user whose code is still valid.
    """
    if request.user.phone_verified:
        return redirect('account')
    if not _otp_expired(request):
        # Server says the code is still alive — ignore and stay on the page.
        return redirect('verify_phone')
    return _cancel_and_delete(request, reason='expired')


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


@login_required
def account_settings(request):
    """Settings: change name + username (one form), change password (requires the
    current password). A separate 'forgot password' escape exists for users who
    don't remember their current password."""
    profile_form = ProfileForm(instance=request.user)
    password_form = ChangePasswordForm(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'profile':
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Ma'lumotlar yangilandi.")
                return redirect('account_settings')
        elif action == 'password':
            password_form = ChangePasswordForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Keep the user logged in after a password change.
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Parol yangilandi.")
                return redirect('account_settings')

    return render(request, 'user/account_settings.html', {
        'profile_form': profile_form,
        'password_form': password_form,
    })


@login_required
@require_POST
def account_forgot_password(request):
    """For a logged-in user who doesn't remember their current password: log them
    out and send them into the phone-OTP reset flow (which requires being
    anonymous)."""
    logout(request)
    return redirect('password_reset_request')


# ============================================================================
# Password reset (phone OTP)  —  request phone -> verify code -> set new password
# Uses its own pwreset_* session keys so it never collides with the signup OTP.
# ============================================================================

PWRESET_TTL_SECONDS = 5 * 60
PWRESET_RESEND_COOLDOWN = 60
PWRESET_MAX_ATTEMPTS = 5          # wrong-code tries before the code is invalidated

PWRESET_REASONS = {
    'expired': "Kod muddati tugadi. Iltimos, qaytadan urinib ko'ring.",
}


def _pwreset_expired(request):
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def _pwreset_ttl(request):
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def _pwreset_cooldown(request):
    raw = request.session.get('pwreset_last_sent_at')
    if not raw:
        return 0
    try:
        last = timezone.datetime.fromisoformat(raw)
        return max(0, int(PWRESET_RESEND_COOLDOWN - (timezone.now() - last).total_seconds()))
    except ValueError:
        return 0


def _pwreset_clear(request):
    for k in ('pwreset_code', 'pwreset_expires_at', 'pwreset_last_sent_at',
              'pwreset_user_id', 'pwreset_phone', 'pwreset_verified', 'pwreset_attempts'):
        request.session.pop(k, None)


def _pwreset_issue_code(request, user):
    """Generate + 'send' a fresh code for an existing user, refreshing last_sent."""
    code = f"{random.randint(0, 999999):06d}"
    request.session['pwreset_code'] = code
    request.session['pwreset_user_id'] = user.id
    request.session['pwreset_last_sent_at'] = timezone.now().isoformat()
    request.session['pwreset_attempts'] = 0   # fresh code -> reset the attempt counter
    send_sms(user.phone,
             f"Vallaymade saytida parolni tiklash uchun kodingiz: {code}")
    return code


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect('account')

    form = ForgotPasswordForm(request.POST or None)
    limited = is_currently_limited(request, 'pwreset_req_ip', 50)
    if request.method == 'POST':
        phone_raw = request.POST.get('phone', '')
        if (is_rate_limited(request, 'pwreset_req_ip', 50, 3600)
                or is_rate_limited(request, 'pwreset_req_phone', 4, 600, ident=phone_raw)):
            limited = True
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            phone = form.cleaned_data['phone']
            user = User.objects.filter(phone=phone).first()

            # Always clear any stale reset state first, so a previous (possibly
            # verified) attempt can't carry over and let someone skip the OTP step.
            _pwreset_clear(request)

            if not user:
                # Per product decision, tell the user the number isn't registered.
                # (Trade-off: this allows phone-number enumeration.)
                form.add_error('phone', "Ushbu raqam ro'yxatdan o'tmagan.")
            else:
                request.session['pwreset_expires_at'] = (
                    timezone.now() + timedelta(seconds=PWRESET_TTL_SECONDS)
                ).isoformat()
                request.session['pwreset_phone'] = phone
                _pwreset_issue_code(request, user)  # sets code, user_id, last_sent_at
                messages.info(request, "Tasdiqlash kodi yuborildi.")
                return redirect('password_reset_verify')

    notice = PWRESET_REASONS.get(request.GET.get('reason'))
    return render(request, 'user/password_reset_request.html', {'form': form, 'notice': notice, 'rate_limited': limited})


def password_reset_verify(request):
    if request.user.is_authenticated:
        return redirect('account')
    if 'pwreset_expires_at' not in request.session:
        return redirect('password_reset_request')
    if _pwreset_expired(request):
        _pwreset_clear(request)
        return redirect(f"{reverse('password_reset_request')}?reason=expired")

    form = OTPForm(request.POST or None)
    if request.method == 'POST':
        uid = str(request.session.get('pwreset_user_id') or '')
        if is_rate_limited(request, 'pwreset_verify', 20, 300, ident=uid):
            messages.error(request, RATE_LIMIT_MESSAGE)
        elif form.is_valid():
            stored = request.session.get('pwreset_code')
            if stored and form.cleaned_data['code'] == stored:
                # Code accepted. Grant a fresh window for the set-password step and
                # retire the code so it can't be reused.
                request.session['pwreset_verified'] = True
                request.session['pwreset_expires_at'] = (
                    timezone.now() + timedelta(seconds=PWRESET_TTL_SECONDS)
                ).isoformat()
                request.session.pop('pwreset_code', None)
                request.session.pop('pwreset_attempts', None)
                return redirect('password_reset_set')

            # Wrong code -> count the attempt; after too many, invalidate the code
            # so it can't be brute-forced within the window.
            attempts = request.session.get('pwreset_attempts', 0) + 1
            request.session['pwreset_attempts'] = attempts
            if attempts >= PWRESET_MAX_ATTEMPTS:
                _pwreset_clear(request)
                messages.error(request, "Juda ko'p urinish. Iltimos, qaytadan urinib ko'ring.")
                return redirect('password_reset_request')
            form.add_error('code', "Kod noto'g'ri.")

    uid_peek = str(request.session.get('pwreset_user_id') or '')
    return render(request, 'user/password_reset_verify.html', {
        'form': form,
        'phone': request.session.get('pwreset_phone', ''),
        'resend_in': _pwreset_cooldown(request),
        'ttl': _pwreset_ttl(request),
        'rate_limited': is_currently_limited(request, 'pwreset_verify', 20, ident=uid_peek),
        'resend_limited': is_currently_limited(request, 'pwreset_resend', 5, ident=uid_peek),
    })


@require_POST
def password_reset_resend(request):
    if 'pwreset_expires_at' not in request.session:
        return redirect('password_reset_request')
    if _pwreset_expired(request):
        _pwreset_clear(request)
        return redirect(f"{reverse('password_reset_request')}?reason=expired")
    if _pwreset_cooldown(request) > 0:
        messages.error(request, "Iltimos biroz kuting.")
        return redirect('password_reset_verify')

    uid = request.session.get('pwreset_user_id')
    if is_rate_limited(request, 'pwreset_resend', 5, 600, ident=str(uid or '')):
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect('password_reset_verify')
    if uid:
        user = User.objects.filter(pk=uid).first()
        if user:
            _pwreset_issue_code(request, user)

    messages.info(request, "Yangi kod yuborildi.")
    return redirect('password_reset_verify')


@require_POST
def password_reset_expire(request):
    # Mirror of expire_verification: only act if the window has genuinely passed,
    # so a forged/early POST can't wipe an in-progress reset.
    if 'pwreset_expires_at' in request.session and not _pwreset_expired(request):
        return redirect('password_reset_verify')
    _pwreset_clear(request)
    return redirect(f"{reverse('password_reset_request')}?reason=expired")


def password_reset_set(request):
    if request.user.is_authenticated:
        return redirect('account')
    # Must have passed the OTP step.
    if not request.session.get('pwreset_verified') or 'pwreset_user_id' not in request.session:
        return redirect('password_reset_request')
    if _pwreset_expired(request):
        _pwreset_clear(request)
        return redirect(f"{reverse('password_reset_request')}?reason=expired")

    user = User.objects.filter(pk=request.session['pwreset_user_id']).first()
    if not user:
        _pwreset_clear(request)
        return redirect('password_reset_request')

    form = ResetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _pwreset_clear(request)
        messages.success(request, "Parol yangilandi. Endi kirishingiz mumkin.")
        return redirect('login')

    return render(request, 'user/password_reset_set.html', {
        'form': form,
        'username': user.username,
        'phone': user.phone,
    })
