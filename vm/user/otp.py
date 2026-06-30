"""
Signup phone-verification OTP.

Owns the OTP session state for the signup -> verify flow: generating/sending the
code, the absolute 5-minute expiry, and the resend cooldown. Views call into here
instead of touching request.session directly, so the OTP rules live in one place.

Session keys used: otp_code, otp_expires_at, otp_last_sent_at.
"""
import random
from datetime import timedelta

from django.utils import timezone

from core.sms import send_sms

TTL_SECONDS = 5 * 60        # 5 minutes — absolute, not reset by resend
RESEND_COOLDOWN = 60        # 60 seconds between resends
MAX_ATTEMPTS = 7            # wrong-code tries before the throwaway account is dropped


def generate(request, reset_expiry):
    """
    Create a fresh 6-digit code and SMS it.
    - reset_expiry=True  -> start a brand new 5-minute window (used on signup)
    - reset_expiry=False -> keep the existing absolute expiry (used on resend)
    """
    code = f"{random.randint(0, 999999):06d}"
    if reset_expiry or 'otp_expires_at' not in request.session:
        expires_at = timezone.now() + timedelta(seconds=TTL_SECONDS)
        request.session['otp_expires_at'] = expires_at.isoformat()
    request.session['otp_code'] = code
    request.session['otp_last_sent_at'] = timezone.now().isoformat()
    request.session['otp_attempts'] = 0   # fresh code -> reset the wrong-try counter
    send_sms(request.user.phone,
             f"Vallaymade saytida ro'yhatdan o'tish uchun kodingiz: {code}")
    return code


def is_expired(request):
    raw = request.session.get('otp_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def ttl_remaining(request):
    raw = request.session.get('otp_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def resend_cooldown(request):
    raw = request.session.get('otp_last_sent_at')
    if not raw:
        return 0
    try:
        last = timezone.datetime.fromisoformat(raw)
        elapsed = (timezone.now() - last).total_seconds()
        return max(0, int(RESEND_COOLDOWN - elapsed))
    except ValueError:
        return 0


def clear(request):
    """Drop the signup OTP keys from the session (after a successful verify)."""
    for k in ('otp_code', 'otp_expires_at', 'otp_last_sent_at', 'otp_attempts'):
        request.session.pop(k, None)


def register_failed_attempt(request):
    """Count a wrong-code try; returns the new attempt total."""
    attempts = request.session.get('otp_attempts', 0) + 1
    request.session['otp_attempts'] = attempts
    return attempts
