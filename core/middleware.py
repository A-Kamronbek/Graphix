"""The Content-Security-Policy, minted per request so it can carry a nonce.

§9 Phase 10 item 2 asks for CSP and §17 #239 settled the shape: our own
middleware rather than a static header in nginx, because nginx cannot mint a
per-request nonce and a static policy would therefore need
``script-src 'unsafe-inline'`` — which is most of what a policy is for.
Django ships no CSP support and `django-csp` is a dependency this project is
not taking (§4; the one exception is `redis`, §17 #240).

**Two policies, not one.** Google's Maps JavaScript API cannot run under a
strict policy: Google's own guidance requires ``'unsafe-eval'`` and ``blob:``
in `script-src`, a `worker-src`, and several of their origins in `img-src` and
`connect-src`. Applying that everywhere would buy the map at the price of every
other page on the site. So the strict policy is the default and the Maps
additions are attached only where the Maps script can actually load, which is
two places and only two: the checkout, whose `map.js` fetches it when the
customer presses "Xaritadan", and the Django admin, whose `admin_map.js` shows
a dropped pin on an order. A test asserts nothing else includes `map.js`, so a
third page cannot quietly appear without this list being updated.

``style-src`` keeps ``'unsafe-inline'`` on every page, deliberately: the rating
bar's width is a ``style="--…"`` custom-property binding and CSS cannot know
the number. That is a real weakening and it is the one the site cannot
currently avoid (§17 #239).
"""
import secrets

from django.urls import Resolver404, resolve

#: Where "Toʻlovga oʻtish" ends up: each gateway's hosted pay page, as a
#: form-action source. Click and Payme build their links on a fixed host -
#: tolov's `my.click.uz/services/pay` and `checkout.paycom.uz` - while Octo's
#: link comes back from its API, so Octo is the one wildcard. A test builds
#: real Click and Payme links and checks their hosts against the policy the
#: payment page is served with, and fails if a gateway is added without a
#: line here (§17 #298).
PAY_PAGES = ('https://my.click.uz', 'https://checkout.paycom.uz',
             'https://*.octo.uz')

#: The policy every page gets. Values are lists so the Maps pages can extend
#: them without either copy drifting from the other.
BASE_POLICY = {
    'default-src': ["'self'"],
    # 'self' plus the nonce. No 'unsafe-inline', which is the whole point:
    # an injected <script> has no nonce and does not run.
    'script-src': ["'self'"],
    # See the module docstring. 'unsafe-inline' here does not let an attacker
    # run code; it lets them restyle the page, which is a much smaller thing.
    'style-src': ["'self'", "'unsafe-inline'"],
    # blob: because the panel checks a photograph before uploading it: it
    # opens the picked file through URL.createObjectURL to read its size.
    # Without blob: the browser refuses that address, and every photograph
    # failed the check as "not an image" (§17 #296). A blob: address is made by
    # the page itself from a file the person chose, so it lets nothing in.
    'img-src': ["'self'", 'data:', 'blob:'],
    'font-src': ["'self'"],
    'connect-src': ["'self'"],
    # Nothing on this site is a plugin, an applet or an embedded object.
    'object-src': ["'none'"],
    # Stops an injected <base> rewriting every relative URL on the page.
    'base-uri': ["'self'"],
    # Every form on the site posts to this origin - checked, not assumed. But
    # the pay button posts to payment_start, which answers with a 302 to the
    # gateway, and browsers hold every redirect after a form submission to
    # this directive as well. With 'self' alone the redirect was refused and
    # a plain click on "Toʻlovga oʻtish" did nothing (§17 #298).
    'form-action': ["'self'", *PAY_PAGES],
    # The same statement as X-Frame-Options: DENY, in the modern header.
    'frame-ancestors': ["'none'"],
}

#: What Google Maps needs on top, from Google's own CSP guidance. Extends the
#: lists above rather than replacing them.
MAPS_POLICY = {
    # 'unsafe-eval' and blob: are Google's requirement, not a convenience.
    # Without them the Maps script does not start at all.
    'script-src': ["'unsafe-eval'", 'blob:', 'https://maps.googleapis.com',
                   'https://maps.gstatic.com', 'https://*.googleapis.com',
                   'https://*.gstatic.com'],
    'style-src': ['https://fonts.googleapis.com'],
    # No blob: here: the base policy has it, and a source listed in both
    # would be sent twice.
    'img-src': ['https://*.googleapis.com', 'https://*.gstatic.com',
                'https://*.google.com', 'https://*.googleusercontent.com',
                'https://*.ggpht.com'],
    'connect-src': ['blob:', 'data:', 'https://*.googleapis.com',
                    'https://*.google.com', 'https://*.gstatic.com'],
    'font-src': ['https://fonts.gstatic.com'],
    'frame-src': ['https://*.google.com'],
    'worker-src': ['blob:'],
}

#: URL names whose page can load the Maps script.
MAPS_VIEWS = frozenset({'checkout'})

#: Paths whose pages can, where there is no URL name of ours to match on.
#: The Django admin's order form shows a dropped pin (`payment/admin.py`).
MAPS_PREFIXES = ('/admin/',)


def wants_maps(request):
    """Whether this request's page may load the Google Maps script.

    Resolved by URL name rather than by path, because every storefront path
    carries a language prefix and matching `/uz/checkout/` would silently miss
    `/ru/checkout/`. The admin has no name of ours, so it matches by prefix.
    """
    for prefix in MAPS_PREFIXES:
        if request.path.startswith(prefix):
            return True
    try:
        return resolve(request.path_info).url_name in MAPS_VIEWS
    except Resolver404:
        return False


def build_policy(nonce, maps=False):
    """The header value: the base policy, the nonce, and Maps if asked.

    Returned sorted so the header is stable between requests - a policy that
    reorders itself every response is one nobody can diff against yesterday's.
    """
    policy = {key: list(values) for key, values in BASE_POLICY.items()}
    policy['script-src'].append("'nonce-%s'" % nonce)
    if maps:
        for key, values in MAPS_POLICY.items():
            policy.setdefault(key, []).extend(values)
    parts = ['%s %s' % (key, ' '.join(values))
             for key, values in sorted(policy.items())]
    # Not a source list, so it is appended rather than joined with one.
    parts.append('upgrade-insecure-requests')
    return '; '.join(parts)


class ContentSecurityPolicyMiddleware:
    """Attach a per-request nonce, then a policy that names it.

    The nonce goes on the request before the view runs, so the one inline
    `<script>` on the site - the JSON-LD block in `base.html` - can render it.
    The header goes on the way out, because only then do we know whether the
    response is HTML worth policing.

    Non-HTML responses are skipped. A policy on a JSON webhook reply protects
    nothing and would be one more thing on the wire for a gateway to read.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 16 bytes of urlsafe base64. A nonce must be unguessable and must
        # never repeat across responses, or it stops being a nonce.
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)

        if 'Content-Security-Policy' in response.headers:
            # Somebody below us set one deliberately; do not argue with it.
            return response
        if not response.headers.get('Content-Type', '').startswith('text/html'):
            return response

        response.headers['Content-Security-Policy'] = build_policy(
            request.csp_nonce, maps=wants_maps(request))
        return response
