"""Password-reset OTP lifecycle, stored in the session.

Mirrors :mod:`user.otp` but for the forgotten-password flow: it issues a code,
tracks expiry/resend/attempts, and additionally remembers which user is being
reset and whether the code has been verified.
"""
import random
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.sms import send_sms

# Password-reset OTP policy: 5-minute validity, 60s resend cooldown, 7 tries max.
TTL_SECONDS = 5 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 7

# User-facing reasons for aborting the reset flow, keyed by an internal code.
REASONS = {
    'expired': _("Kod muddati tugadi. Iltimos, qaytadan urinib koʻring."),
}


def is_expired(request):
    """Return True if no reset window exists or the current one has elapsed."""
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def ttl_remaining(request):
    """Return seconds left before the reset code expires (0 if expired/absent)."""
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def resend_cooldown(request):
    """Return seconds the user must still wait before a resend is allowed."""
    raw = request.session.get('pwreset_last_sent_at')
    if not raw:
        return 0
    try:
        last = timezone.datetime.fromisoformat(raw)
        return max(0, int(RESEND_COOLDOWN - (timezone.now() - last).total_seconds()))
    except ValueError:
        return 0


def clear(request):
    """Drop all password-reset keys from the session."""
    for k in ('pwreset_code', 'pwreset_expires_at', 'pwreset_last_sent_at',
              'pwreset_user_id', 'pwreset_phone', 'pwreset_verified', 'pwreset_attempts'):
        request.session.pop(k, None)


def start_window(request, phone):
    """Open a reset window for ``phone`` without issuing a code yet."""
    request.session['pwreset_expires_at'] = (
        timezone.now() + timedelta(seconds=TTL_SECONDS)
    ).isoformat()
    request.session['pwreset_phone'] = phone


def issue_code(request, user):
    """Generate a reset code, store it against ``user``, and SMS it.

    Resets the failed-attempt counter so a freshly issued code always starts
    with a clean slate. Returns the generated six-digit code.
    """
    code = f"{random.randint(0, 999999):06d}"
    request.session['pwreset_code'] = code
    request.session['pwreset_user_id'] = user.id
    request.session['pwreset_last_sent_at'] = timezone.now().isoformat()
    request.session['pwreset_attempts'] = 0   # fresh code -> reset the attempt counter
    send_sms(user.phone,
             f"GRAPHIX saytida parolni tiklash uchun kodingiz: {code}")
    return code


def mark_verified(request):
    """Mark the reset code as verified and refresh the window for the password step.

    Clears the code and attempt counter (they're no longer needed) and extends
    the expiry so the user has the full TTL to choose a new password.
    """
    request.session['pwreset_verified'] = True
    request.session['pwreset_expires_at'] = (
        timezone.now() + timedelta(seconds=TTL_SECONDS)
    ).isoformat()
    request.session.pop('pwreset_code', None)
    request.session.pop('pwreset_attempts', None)


def register_failed_attempt(request):
    """Increment and return the failed-attempt counter for the current code."""
    attempts = request.session.get('pwreset_attempts', 0) + 1
    request.session['pwreset_attempts'] = attempts
    return attempts
