"""
Lightweight, fail-open rate limiting built on Django's cache framework.

Why hand-rolled instead of a third-party package:
  * No external dependency -> no version/compat risk with the Django release.
  * FAIL OPEN: if the cache misbehaves or anything raises, requests are allowed
    through. Rate limiting must never take the site down.

It's a fixed-window counter keyed by an identity you choose (client IP, the
authenticated user, or a submitted field like username/phone). Keying on the
submitted account is deliberate: behind a reverse proxy every request can share
one IP, so an IP-only limit could lock everyone out — account-keyed limits stay
correct regardless of proxy setup.

Production note: the default cache is per-process LocMemCache, so with multiple
gunicorn workers each worker counts separately (limits become "per worker").
For strict global limits, point the 'default' cache at Redis or the database
cache. Until then this still works and still fails open.
"""
from hashlib import md5
from django.core.cache import cache


# Shown to the user (via messages.error) when a limit trips.
RATE_LIMIT_MESSAGE = "Juda ko'p urinish. Iltimos, birozdan so'ng qayta urinib ko'ring."


def client_ip(request):
    """Best-effort client IP. Honors the first hop of X-Forwarded-For when
    present (what nginx passes once configured); otherwise REMOTE_ADDR."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _bucket_key(scope, ident):
    digest = md5(f"{scope}:{ident}".encode('utf-8', 'ignore')).hexdigest()
    return f"rl:{scope}:{digest}"


def is_rate_limited(request, scope, limit, window, ident=None):
    """
    Returns True if this caller has EXCEEDED `limit` hits within `window`
    seconds for `scope`. Always counts the current call.

    ident: identity to bucket on (e.g. a username or phone). If None/empty,
           the client IP is used.

    Fails OPEN (returns False) on any error, so a cache problem can never break
    a view.
    """
    try:
        if not ident:
            ident = client_ip(request)
        key = _bucket_key(scope, ident)
        # add() only sets the value+TTL if the key is absent, so the window is
        # fixed from the first hit; incr() preserves that TTL.
        cache.add(key, 0, timeout=window)
        try:
            count = cache.incr(key)
        except ValueError:
            # Key expired between add() and incr(); treat as a fresh window.
            cache.add(key, 0, timeout=window)
            count = cache.incr(key)
        return count > limit
    except Exception:
        return False


def is_currently_limited(request, scope, limit, ident=None):
    """
    Read-only check: is this caller already AT/OVER the limit right now? Does
    NOT increment the counter, so it's safe to call when rendering a page (e.g.
    to disable a button). Returns True when the *next* attempt would be blocked.

    Fails OPEN (returns False) on any error.
    """
    try:
        if not ident:
            ident = client_ip(request)
        count = cache.get(_bucket_key(scope, ident), 0) or 0
        return count >= limit
    except Exception:
        return False
