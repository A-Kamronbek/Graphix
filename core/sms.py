"""Eskiz.uz SMS gateway client.

Authenticates against the Eskiz REST API, caches the JWT token, and sends the
signup / password-reset OTP messages. Failures are logged and swallowed so an
SMS outage can't 500 a signup.
"""
import logging
import re
import requests
from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)

ESKIZ_BASE = "https://notify.eskiz.uz/api"
_TOKEN_CACHE_KEY = "eskiz_sms_token"


def _login():
    """Authenticate with Eskiz and cache a fresh JWT token."""
    resp = requests.post(
        f"{ESKIZ_BASE}/auth/login",
        data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["data"]["token"]
    # Eskiz tokens last ~30 days; cache for 25 to refresh well before expiry.
    cache.set(_TOKEN_CACHE_KEY, token, 60 * 60 * 24 * 25)
    return token


def _get_token(force_refresh=False):
    """Return the cached token, logging in if missing or ``force_refresh``."""
    token = None if force_refresh else cache.get(_TOKEN_CACHE_KEY)
    return token or _login()


def _format_phone(phone):
    """Reduce a number to the digits-only form Eskiz expects (998XXXXXXXXX)."""
    return re.sub(r"\D", "", phone)


def send_sms(phone, message):
    """Send one SMS via Eskiz; return True on success, False on failure (logged).

    Retries once with a fresh token on a 401 (expired token), and never raises,
    so a gateway error degrades gracefully instead of breaking the caller.
    """
    payload = {
        "mobile_phone": _format_phone(phone),
        "message": message,
        "from": settings.ESKIZ_FROM,
    }

    def _post(token):
        return requests.post(
            f"{ESKIZ_BASE}/message/sms/send",
            data=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

    try:
        resp = _post(_get_token())
        if resp.status_code == 401:
            resp = _post(_get_token(force_refresh=True))
        if resp.status_code >= 400:
            logger.error("Eskiz SMS rejected for %s (%s): %s",
                         _format_phone(phone), resp.status_code, resp.text)
            return False
        return True
    except requests.RequestException as e:
        logger.error("Eskiz SMS request error for %s: %s", _format_phone(phone), e)
        return False
