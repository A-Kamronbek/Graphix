"""Fold a guest's cart into their account when they sign in, by any door.

The merge used to be called by the storefront's sign-in and sign-up views.
That left every other caller of ``login()`` out, and there is one the shop
uses daily: the Django admin's own sign-in form. Hanging the merge off
Django's signed-in signal means a new way in cannot forget it.
"""
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .services import merge_guest_cart


@receiver(user_logged_in)
def merge_cart_on_sign_in(sender, request, user, **kwargs):
    """Merge the cart of the session that just signed in into ``user``'s.

    The guest cart is keyed to the session key the visitor arrived with.
    ``login()`` has already replaced that key by the time this runs, so it is
    read from the request's cookie, which is the key as the browser sent it.
    A sign-in with no request or no cookie has no guest cart to bring.
    """
    if request is None:
        return
    merge_guest_cart(request.COOKIES.get(settings.SESSION_COOKIE_NAME), user)
