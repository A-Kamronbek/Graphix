"""Cache-backed rate limiting: dependency-free and fail-open.

Counters live in the Django cache under hashed keys. Every check is wrapped so a
cache outage never blocks a request (fail-open): if the backend errors, the hit
is allowed through rather than denied.
"""
from hashlib import md5
from django.core.cache import cache


RATE_LIMIT_MESSAGE = "Juda ko'p urinish. Iltimos, birozdan so'ng qayta urinib ko'ring."


def client_ip(request):
    """Best-effort client IP, preferring the first X-Forwarded-For hop (set by nginx)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _bucket_key(scope, ident):
    """Build a hashed cache key for a (scope, identity) counter."""
    digest = md5(f"{scope}:{ident}".encode('utf-8', 'ignore')).hexdigest()
    return f"rl:{scope}:{digest}"


def is_rate_limited(request, scope, limit, window, ident=None):
    """Count this hit and return True if it exceeds ``limit`` within ``window`` seconds.

    Identity defaults to the client IP; pass ``ident`` to limit per user/phone.
    Fails open: any cache error returns False (treated as not limited).
    """
    try:
        if not ident:
            ident = client_ip(request)
        key = _bucket_key(scope, ident)
        cache.add(key, 0, timeout=window)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.add(key, 0, timeout=window)
            count = cache.incr(key)
        return count > limit
    except Exception:
        return False


def is_currently_limited(request, scope, limit, ident=None):
    """Read-only check of whether the counter is already at/over ``limit``.

    Used to render the disabled/limited UI state without incrementing the count.
    """
    try:
        if not ident:
            ident = client_ip(request)
        count = cache.get(_bucket_key(scope, ident), 0) or 0
        return count >= limit
    except Exception:
        return False
