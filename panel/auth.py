"""Who may open the panel, and the door staff come in by.

Django ships ``staff_member_required``, and it is the wrong decorator here: it
sends **everyone** who fails to the *admin* login form, so a signed-in customer
who guesses the URL is shown a second login page and invited to try again. The
Definition of Done says non-staff get 403, and it is right — a customer who is
already signed in has not mistyped a password, they are somewhere they should
not be, and the honest answer is "no", not "try again".

An anonymous visitor is a different case and gets a sign-in form with a
``next``, because the person that actually happens to is the owner on a phone
whose session has expired. The form is the Django admin's: the shop's own
sign-in is by SMS code and is for customers, and staff sign in with a password
(§17 #309).

Every panel response is also marked never-cache, for the same reason Django's
own admin does it: these pages carry customers' names, phone numbers and
addresses, and a page held in the back/forward cache is a page still readable
after somebody signs out on a shared laptop.
"""
import unicodedata
from functools import wraps
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache

from core.ratelimit import RATE_LIMIT_MESSAGE, is_rate_limited


def staff_only(view):
    """Staff pass; signed-in customers get 403; anonymous visitors get the staff sign-in."""
    @wraps(view)
    def guard(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"{reverse('admin:login')}?{urlencode({'next': request.get_full_path()})}")
        if not user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return never_cache(guard)


def staff_sign_in(request):
    """The Django admin's sign-in form, with a limit on guesses.

    Django's form has none: a script can try passwords against it for as long
    as it likes. It is the only door staff have (§17 #309), and what is behind
    it is every customer's name, number and address. The figures are the ones
    the shop's own password sign-in used while it had one: eight tries at a
    name and sixty from an address, in five minutes.

    The name is counted in the form Django looks it up in. Its form folds
    look-alike characters together before the lookup, so a name typed in
    full-width letters is the same account, and counted as typed it would be
    a fresh eight tries each time.
    """
    if request.method == 'POST':
        name = unicodedata.normalize('NFKC', request.POST.get('username', '')).strip().casefold()
        limited = is_rate_limited(request, 'staff_login_address', 60, 300)
        if name and is_rate_limited(request, 'staff_login_name', 8, 300, ident=name):
            limited = True
        if limited:
            messages.error(request, RATE_LIMIT_MESSAGE)
            return redirect(request.get_full_path())
    return admin.site.login(request)
