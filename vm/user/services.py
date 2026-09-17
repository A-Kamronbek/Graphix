"""Account operations that are shared between the views and the middleware.

There are two places that drop an abandoned signup — ``_cancel_and_delete`` in
``user.views`` and ``PhoneVerificationMiddleware`` when the OTP window lapses —
and they must agree about when that is safe. A guard written in one and not the
other is how a customer's cart quietly disappears, so the rule lives here and
both call it (§12 risk #4).
"""
import logging

from cart.models import Cart
from payment.models import Order

logger = logging.getLogger(__name__)


def is_disposable(user):
    """Is this an abandoned signup with nothing hanging off it?

    An unverified account is throwaway *until* something of the customer's is
    attached to it. Both checks matter:

    * an order — the shop's own record of a sale. Since §17 #219 the database
      refuses to delete an account that has one (``PROTECT``); checking first
      means this path never relies on that refusal;
    * a cart — a CASCADE relation, and for an unverified user a guest cart that
      was claimed at signup. Deleting the account throws away what they were
      about to buy.
    """
    if not user or not user.is_authenticated or getattr(user, 'phone_verified', True):
        return False
    return not (Order.objects.filter(user=user).exists()
                or Cart.objects.filter(user=user).exists())


def delete_if_disposable(user):
    """Delete an abandoned signup; return whether it was actually deleted.

    Never raises: this runs on paths whose job is to get the visitor back to
    the signup page, and failing to tidy up must not turn into a 500.
    """
    if not is_disposable(user):
        return False
    try:
        user.delete()
    except Exception:
        logger.exception('could not delete unverified user %s', user.pk)
        return False
    return True
