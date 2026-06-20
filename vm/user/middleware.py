from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


class PhoneVerificationMiddleware:
    """
    Forces authenticated users with phone_verified=False onto the OTP page.

    Allowlist (always accessible without verification):
      - the verify/resend OTP endpoints themselves
      - logout
      - the admin site
      - static & media
    """

    # URL *names* that should never be blocked.
    EXEMPT_URL_NAMES = {'verify_phone', 'resend_otp', 'cancel_verification', 'expire_verification', 'logout'}

    # Path *prefixes* that should never be blocked.
    EXEMPT_PATH_PREFIXES = ('/admin/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response
        # Resolve exempt URL names once at startup. If a name is missing
        # (e.g. during early migrations), just skip it silently.
        self._exempt_paths = set()
        for name in self.EXEMPT_URL_NAMES:
            try:
                self._exempt_paths.add(reverse(name))
            except NoReverseMatch:
                pass

    def __call__(self, request):
        user = getattr(request, 'user', None)

        # Anonymous users + already-verified users: pass through.
        if not user or not user.is_authenticated or getattr(user, 'phone_verified', True):
            return self.get_response(request)

        path = request.path

        # Allowlist check.
        if path in self._exempt_paths:
            return self.get_response(request)
        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        # Anything else -> back to OTP page.
        return redirect('verify_phone')
