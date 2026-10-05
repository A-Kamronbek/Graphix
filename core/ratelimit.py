"""Cache-backed rate limiting: dependency-free and fail-open.

Counters live in the Django cache under hashed keys. Every check is wrapped so a
cache outage never blocks a request (fail-open): if the backend errors, the hit
is allowed through rather than denied.
"""
from hashlib import md5
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _


RATE_LIMIT_MESSAGE = _("Juda koʻp urinish. Iltimos, birozdan soʻng qayta urinib koʻring.")

#: The longest window any limit on the site may use. The privacy policy tells
#: a visitor how long the hashed counter behind their IP address can live, and
#: a test holds every call in the project to this ceiling.
MAX_WINDOW = 60 * 60


def client_ip(request):
    """The client's address as nginx saw it: the last X-Forwarded-For hop.

    nginx appends the address of whoever connected to it to whatever
    X-Forwarded-For the request arrived with, so the last hop is the only one
    the client did not write. The first hop is the client's own claim, and
    reading it let anyone step around every IP-keyed limit on the site by
    sending a new invented address with each request.

    This is right while exactly one proxy stands in front of gunicorn, which
    is what deploy/nginx/graphix.conf sets up. A second one - a CDN, a load
    balancer - would make the last hop that proxy's address, and this function
    is then the thing to change.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    last_hop = xff.split(',')[-1].strip()
    if last_hop:
        return last_hop
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
