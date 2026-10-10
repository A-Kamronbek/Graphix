"""Middleware that holds a signed-in account to a confirmed phone number."""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.utils import translation


class PhoneVerificationMiddleware:
    """Send a signed-in account with an unconfirmed number to the code page.

    A customer's number is confirmed before their account exists, so the only
    account this still catches is one made in the Django admin, which is how
    staff are made (§17 #227). It can reach the admin, where the box can be
    ticked for it, and the code page, where it can confirm the number itself.
    """
    EXEMPT_URL_NAMES = {'verify_phone', 'resend_otp', 'cancel_verification', 'expire_verification', 'logout'}

    # `/i18n/` is the language switch: someone waiting for a code may still
    # change the language of the page they are waiting on.
    EXEMPT_PATH_PREFIXES = ('/admin/', '/static/', '/media/', '/i18n/')

    def __init__(self, get_response):
        """Resolve exempt URL names to paths once at startup, in every language.

        The names live inside ``i18n_patterns``, so each one has a path per
        language. Resolved in the default language alone, only the Uzbek
        pages were exempt: an unverified account on ``/ru/verify-phone/`` or
        ``/en/verify-phone/`` was redirected to the page it was already on,
        for ever, and could neither verify nor sign out (§17 #225).
        """
        self.get_response = get_response
        self._exempt_paths = set()
        for code, _label in settings.LANGUAGES:
            with translation.override(code):
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

        return redirect('verify_phone')
