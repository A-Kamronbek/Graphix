"""Who may open the panel.

Django ships ``staff_member_required``, and it is the wrong decorator here: it
sends **everyone** who fails to the *admin* login form, so a signed-in customer
who guesses the URL is shown a second login page and invited to try again. The
Definition of Done says non-staff get 403, and it is right — a customer who is
already signed in has not mistyped a password, they are somewhere they should
not be, and the honest answer is "no", not "try again".

An anonymous visitor is a different case and gets the site's own login form
with a ``next``, because the person that actually happens to is the owner on a
phone whose session has expired.
"""
from functools import wraps
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


def staff_only(view):
    """Staff pass; signed-in customers get 403; anonymous visitors get login."""
    @wraps(view)
    def guard(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"{reverse('login')}?{urlencode({'next': request.get_full_path()})}")
        if not user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return guard
