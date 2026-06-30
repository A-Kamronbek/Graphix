"""Middleware that forces phone verification before the site can be used."""
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.utils import timezone


class PhoneVerificationMiddleware:
    """Redirect unverified users to OTP entry; delete them if the window lapsed.

    Authenticated users whose phone isn't verified are sent to ``verify_phone``
    for every non-exempt path. If their OTP window has already expired, the
    half-registered account is removed and they're bounced back to signup.
    """
    EXEMPT_URL_NAMES = {'verify_phone', 'resend_otp', 'cancel_verification', 'expire_verification', 'logout'}

    EXEMPT_PATH_PREFIXES = ('/admin/', '/static/', '/media/')

    def __init__(self, get_response):
        """Resolve exempt URL names to paths once at startup."""
        self.get_response = get_response
        self._exempt_paths = set()
        for name in self.EXEMPT_URL_NAMES:
            try:
                self._exempt_paths.add(reverse(name))
            except NoReverseMatch:
                pass

    def __call__(self, request):
        """Gate each request on the user's phone-verified status."""
        user = getattr(request, 'user', None)

        if not user or not user.is_authenticated or getattr(user, 'phone_verified', True):
            return self.get_response(request)

        path = request.path

        if path in self._exempt_paths:
            return self.get_response(request)
        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        if self._otp_window_expired(request):
            logout(request)
            try:
                user.delete()
            except Exception:
                pass
            return redirect(f"{reverse('signup')}?reason=expired")

        return redirect('verify_phone')

    @staticmethod
    def _otp_window_expired(request):
        """Return True if the signup OTP window has elapsed."""
        raw = request.session.get('otp_expires_at')
        if not raw:
            return False
        try:
            return timezone.now() > timezone.datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return False
