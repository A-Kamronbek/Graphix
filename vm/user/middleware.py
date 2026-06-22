from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.utils import timezone


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

        # Allowlist check (verify/resend/cancel/expire/logout, admin, static, media).
        if path in self._exempt_paths:
            return self.get_response(request)
        if any(path.startswith(p) for p in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        # Unverified user on a gated page. If their OTP window has definitively
        # expired (server clock), the account is a throwaway from an abandoned
        # signup — delete it and send them to signup as a guest, rather than
        # looping them back to the verify page. This is what cleans up accounts
        # for someone who closed the browser mid-verification and returns later.
        if self._otp_window_expired(request):
            logout(request)            # flushes the session
            try:
                user.delete()
            except Exception:
                pass
            return redirect(f"{reverse('signup')}?reason=expired")

        # Window still alive (or never started) -> back to the OTP page.
        return redirect('verify_phone')

    @staticmethod
    def _otp_window_expired(request):
        """
        True only if an OTP window EXISTS and has passed. Absent window returns
        False, so a freshly-logged-in unverified user (no otp_* in session yet)
        is sent to verify_phone to get a code instead of being deleted.
        """
        raw = request.session.get('otp_expires_at')
        if not raw:
            return False
        try:
            return timezone.now() > timezone.datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return False
