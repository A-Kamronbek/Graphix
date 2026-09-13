"""Cart operations: resolve the active cart, match a variant, add/update items.

Every ``CartError`` message reaches the customer through ``messages.error()``,
so it is translated. ``gettext`` rather than ``gettext_lazy``: these are built
inside a request, where the active language is already set, and a lazy object
would only defer the same lookup and then have to survive ``str(exception)``.
"""
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Least
from django.utils.translation import gettext as _

from .models import Cart, CartItem


class CartError(Exception):
    """Raised when a cart operation can't proceed (bad selection or unavailable item)."""


def find_cart(request):
    """Return the visitor's open cart, or None. Never writes anything.

    Reading a cart must not create one. Every crawler that fetches /cart/ would
    otherwise leave a session and a cart row behind, and the prune command would
    spend its life deleting them.
    """
    if request.user.is_authenticated:
        return Cart.objects.filter(user=request.user, status=True).first()
    key = request.session.session_key
    if not key:
        return None
    return Cart.objects.filter(session_key=key, user__isnull=True, status=True).first()


def get_active_cart(request):
    """Return the visitor's open cart, creating one if there isn't one.

    A guest gets a cart keyed to their session, which means a session has to
    exist — so this is called only when something is actually being added, never
    when a page is merely rendered.
    """
    if request.user.is_authenticated:
        cart, _created = Cart.objects.get_or_create(user=request.user, status=True)
        return cart

    if not request.session.session_key:
        request.session.create()
    cart, _created = Cart.objects.get_or_create(
        session_key=request.session.session_key, user=None, status=True
    )
    return cart


@transaction.atomic
def merge_guest_cart(session_key, user):
    """Fold a guest cart into ``user``'s open cart. Returns the surviving cart.

    Called immediately after login and after signup. ``session_key`` is the key
    as it was *before* ``django.contrib.auth.login`` ran: login cycles the
    session key to prevent fixation, so reading it afterwards finds a key no
    cart was ever stored against and the guest's items would simply vanish.

    Both carts are locked for the length of the transaction, because the same
    person may have the shop open in two tabs and submit from both.

    Quantities are summed and capped at what is actually in stock. A new line
    keeps the guest's ``price_stat`` rather than re-reading the catalogue: the
    price was snapshotted when they added it, and signing in is not a reason to
    charge them today's price.
    """
    if not session_key:
        return None

    guest = (Cart.objects.select_for_update()
             .filter(session_key=session_key, user__isnull=True, status=True).first())
    if guest is None:
        return None

    mine = Cart.objects.select_for_update().filter(user=user, status=True).first()
    if mine is None:
        # Nothing to merge into: the guest cart simply becomes theirs. The
        # session key is cleared so the row satisfies the per-user constraint
        # and no later session can claim it again.
        guest.user = user
        guest.session_key = None
        guest.save(update_fields=['user', 'session_key'])
        return guest

    for line in guest.cart_items.select_related('variant'):
        cap = variant_cap(line.variant)
        if cap <= 0:
            continue        # sold out while they were signed out
        existing = CartItem.objects.filter(cart=mine, variant=line.variant).first()
        if existing:
            CartItem.objects.filter(pk=existing.pk).update(
                quantity=Least(F('quantity') + line.quantity, Value(cap))
            )
        else:
            CartItem.objects.create(
                cart=mine, variant=line.variant,
                quantity=min(line.quantity, cap),
                price_stat=line.price_stat,
            )
    guest.delete()
    return mine


def resolve_variant(product, colour_id, size_id):
    """Resolve the single variant matching the chosen colour/size.

    Raises :class:`CartError` if the selection is ambiguous or invalid, if the
    matched variant isn't for sale, or if it has run out. ``available`` is the
    owner's switch and ``stock`` is the count; both have to agree, so they get
    separate messages — "sold out" and "not for sale" mean different things to a
    customer.
    """
    variant_qs = product.variants.all()
    if colour_id:
        variant_qs = variant_qs.filter(colour_id=colour_id)
    if size_id:
        variant_qs = variant_qs.filter(size_id=size_id)

    matches = list(variant_qs[:2])
    if len(matches) != 1:
        raise CartError(_("Tovar notoʻgʻri tanlangan"))
    variant = matches[0]

    if not variant.available:
        raise CartError(_("Ushbu tovar sotuvda yoʻq"))
    if variant.stock <= 0:
        raise CartError(_("Ushbu oʻlcham tugagan"))
    return variant


def variant_cap(variant):
    """Return the most units of ``variant`` one cart line may hold.

    The 99 ceiling is a sanity limit on the quantity widget; ``stock`` is the
    real one. Whichever is lower wins.
    """
    return min(99, variant.stock)


def add_variant(cart, variant, qty):
    """Add ``qty`` of ``variant`` to the cart, or bump an existing line.

    Capped at ``min(99, stock)``. The bump is done with a single ``UPDATE`` using
    ``Least(F('quantity') + qty, cap)`` rather than a Python read-modify-write, so
    two tabs adding the same item can't race past the cap. ``Least`` also pulls an
    existing line back down if stock has fallen below it since it was added.
    """
    cap = variant_cap(variant)
    if cap <= 0:
        raise CartError(_("Ushbu oʻlcham tugagan"))

    item, created = CartItem.objects.get_or_create(
        cart=cart, variant=variant,
        defaults={'quantity': min(qty, cap), 'price_stat': variant.price},
    )
    if not created:
        CartItem.objects.filter(pk=item.pk).update(
            quantity=Least(F('quantity') + qty, Value(cap))
        )
    return item


def set_item_quantity(item, qty):
    """Set a line's quantity, deleting the line when ``qty`` drops to 0 or below.

    Clamped to what is actually in stock, so a hand-edited quantity field can't
    over-order.
    """
    if qty <= 0:
        item.delete()
        return

    cap = variant_cap(item.variant)
    if cap <= 0:
        item.delete()
        raise CartError(_("Ushbu oʻlcham tugagan"))

    item.quantity = min(qty, cap)
    item.save(update_fields=['quantity'])
