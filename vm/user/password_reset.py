"""
Password reset via phone OTP.

Owns the reset session state for the request -> verify -> set-new-password flow.
Uses its own pwreset_* session keys so it never collides with the signup OTP.

Session keys: pwreset_code, pwreset_expires_at, pwreset_last_sent_at,
pwreset_user_id, pwreset_phone, pwreset_verified, pwreset_attempts.
"""
import random
from datetime import timedelta

from django.utils import timezone

from core.sms import send_sms

TTL_SECONDS = 5 * 60
RESEND_COOLDOWN = 60
MAX_ATTEMPTS = 5            # wrong-code tries before the code is invalidated

REASONS = {
    'expired': "Kod muddati tugadi. Iltimos, qaytadan urinib ko'ring.",
}


def is_expired(request):
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return True
    try:
        return timezone.now() > timezone.datetime.fromisoformat(raw)
    except ValueError:
        return True


def ttl_remaining(request):
    raw = request.session.get('pwreset_expires_at')
    if not raw:
        return 0
    try:
        exp = timezone.datetime.fromisoformat(raw)
        return max(0, int((exp - timezone.now()).total_seconds()))
    except ValueError:
        return 0


def resend_cooldown(request):
    raw = request.session.get('pwreset_last_sent_at')
    if not raw:
        return 0
    try:
        last = timezone.datetime.fromisoformat(raw)
        return max(0, int(RESEND_COOLDOWN - (timezone.now() - last).total_seconds()))
    except ValueError:
        return 0


def clear(request):
    for k in ('pwreset_code', 'pwreset_expires_at', 'pwreset_last_sent_at',
              'pwreset_user_id', 'pwreset_phone', 'pwreset_verified', 'pwreset_attempts'):
        request.session.pop(k, None)


def start_window(request, phone):
    """Open a fresh reset window for a phone (the request step)."""
    request.session['pwreset_expires_at'] = (
        timezone.now() + timedelta(seconds=TTL_SECONDS)
    ).isoformat()
    request.session['pwreset_phone'] = phone


def issue_code(request, user):
    """Generate + SMS a fresh code for an existing user, refreshing last_sent."""
    code = f"{random.randint(0, 999999):06d}"
    request.session['pwreset_code'] = code
    request.session['pwreset_user_id'] = user.id
    request.session['pwreset_last_sent_at'] = timezone.now().isoformat()
    request.session['pwreset_attempts'] = 0   # fresh code -> reset the attempt counter
    send_sms(user.phone,
             f"Vallaymade saytida parolni tiklash uchun kodingiz: {code}")
    return code


def mark_verified(request):
    """Code accepted: grant a fresh window for the set-password step and retire
    the code so it can't be reused."""
    request.session['pwreset_verified'] = True
    request.session['pwreset_expires_at'] = (
        timezone.now() + timedelta(seconds=TTL_SECONDS)
    ).isoformat()
    request.session.pop('pwreset_code', None)
    request.session.pop('pwreset_attempts', None)


def register_failed_attempt(request):
    """Count a wrong-code try; returns the new attempt total."""
    attempts = request.session.get('pwreset_attempts', 0) + 1
    request.session['pwreset_attempts'] = attempts
    return attempts
