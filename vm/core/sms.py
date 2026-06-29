import logging
import re
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ESKIZ_BASE = "https://notify.eskiz.uz/api"
_TOKEN_CACHE_KEY = "eskiz_sms_token"


def _login():
    resp = requests.post(
        f"{ESKIZ_BASE}/auth/login",
        data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["data"]["token"]
    cache.set(_TOKEN_CACHE_KEY, token, 60 * 60 * 24 * 25)  # tokens last ~30d; cache 25
    return token


def _get_token(force_refresh=False):
    token = None if force_refresh else cache.get(_TOKEN_CACHE_KEY)
    return token or _login()


def _format_phone(phone):
    """Eskiz wants 998XXXXXXXXX — digits only, no '+' or spaces."""
    return re.sub(r"\D", "", phone)


def send_sms(phone, message):
    """Send one SMS. Returns True on success, False on failure (logged)."""
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