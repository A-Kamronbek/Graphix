"""Changing an order's status, in one place.

There is one function here and everything that moves a status calls it: the
panel, the Django admin, and anything added later. That is the whole point —
the Definition of Done says status changes are logged with who and when, and a
log that depends on every caller remembering to write to it is a log with
holes in it. ``payment.services`` keeps the money paths (§4: do not
restructure ``create_order_from_cart``); this is the staff-facing one.

A move across the line between paid and not paid is more than a label: a
sale holds stock. So the function asks ``payment.services`` to take or give
back what the sale holds whenever a move crosses that line. It did not, for
a long time, and a paid order cancelled from the panel kept its shirts out of
stock (§17 #57).

The function records; it does not decide policy. Which statuses a *panel* user
may set is the panel's business and lives with the view, because the Django
admin is a superuser tool with a different answer. Keeping the two apart is
what lets the admin route through here as well, instead of writing silently.
"""
from django.db import transaction

from payment import services as payment_services
from payment.models import Order, SOLD
from .models import OrderStatusChange

#: What the panel offers. ``paying`` is missing on purpose: an order becomes
#: payable at checkout and leaves that state when Click says so, and pushing it
#: back by hand would leave an order waiting for a payment nobody will attempt
#: again. The Django admin is not bound by this.
PANEL_SETTABLE = [Order.Status.PAID, Order.Status.PROCESSING,
                  Order.Status.ON_THE_WAY, Order.Status.DONE,
                  Order.Status.CANCELLED]

#: The same list as (value, label) pairs, for a <select>. Built here so the
#: control and the check the POST goes through can never offer different sets.
PANEL_CHOICES = [(status.value, status.label) for status in PANEL_SETTABLE]


class UnknownStatus(Exception):
    """The value asked for is not one of ``Order.Status``."""


@transaction.atomic
def set_status(order, status, by=None, note=''):
    """Move ``order`` to ``status`` and record the move. Returns the log row.

    Locks the row first, because two people looking at the same order on two
    phones is the ordinary case in a shop and not the exotic one — without the
    lock the second save silently wins and the history then records a move from
    a status the order was never in.

    A no-op change writes nothing and returns ``None``: re-tapping the status an
    order already has should not fill its history with rows saying so.
    """
    if status not in Order.Status.values:
        raise UnknownStatus(status)

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status == status:
        return None

    previous = locked.status
    # Inside this transaction, so the stock and the status move together or
    # not at all. Moving along after payment (paid to packing to delivered)
    # crosses nothing and takes nothing more.
    if status in SOLD and previous not in SOLD:
        payment_services.take_for_sale(locked)
    elif previous in SOLD and status not in SOLD:
        payment_services.return_from_sale(locked)
    locked.status = status
    locked.save(update_fields=['status', 'updated_at'])

    change = OrderStatusChange.objects.create(
        order=locked, from_status=previous, to_status=status,
        changed_by=by if (by is not None and by.is_authenticated) else None,
        note=note[:200],
    )
    # The caller usually holds a stale copy; keep it honest rather than making
    # every call site remember to refresh it.
    order.status = status
    return change
