"""Signup OTP lifecycle, stored in the session.

A six-digit code is kept in the user's session with an expiry, a resend
cooldown, and a failed-attempt counter. All timestamps are stored as ISO
strings so they survive session serialisation.
"""
import random
from datetime import timedelta

from django.utils import timezone

from core.sms import send_sms

# Signup OTP policy: 5-minute validity, 60s between resends, 7 wrong guesses max.
TTL_SECONDS = 5 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 7


def generate(request, reset_expiry):
    """Create a new OTP, store it in the session, and SMS it to the user.

    Resets the failed-attempt counter on every new code. The expiry window is
    (re)started only when ``reset_expiry`` is true or no window exists yet, so a
    plain resend keeps the original deadline rather than extending it.

    Returns the generated six-digit code.
    """
    code = f"{random.randint(0, 999999):06d}"
    if reset_expiry or 'otp_expires_at' not in request.session:
        expires_at = timezone.now() + timedelta(seconds=TTL_SECONDS)
        request.session['otp_expires_at'] = expires_at.isoformat()
    request.session['otp_code'] = code
    request.session['otp_last_sent_at'] = timezone.now().isoformat()
    request.session['otp_attempts'] = 0
    send_sms(request.user.phone,
             f"GRAPHIX saytida ro'yxatdan o'tish uchun kodingiz: {code}")
    return code


def is_expired(request):
    """Return True if no OTP window exists or the current one has elapsed."""
    raw = request.session.get('otp_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def ttl_remaining(request):
    """Return seconds left before the OTP expires (0 if expired/absent)."""
    raw = request.session.get('otp_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def resend_cooldown(request):
    """Return seconds the user must still wait before a resend is allowed."""
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
    """Drop all OTP-related keys from the session."""
    for k in ('otp_code', 'otp_expires_at', 'otp_last_sent_at', 'otp_attempts'):
        request.session.pop(k, None)


def register_failed_attempt(request):
    """Increment and return the failed-attempt counter for the current code."""
    attempts = request.session.get('otp_attempts', 0) + 1
    request.session['otp_attempts'] = attempts
    return attempts
