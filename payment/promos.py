"""The rules of a promo code: when one may be used, and what it takes off.

Two questions, kept apart because they are asked at different moments.
:func:`check` asks whether this customer may use this code at all: it is on,
inside its dates, not used up, the goods reach its minimum, and the customer
has not used it before. :func:`discount` asks what it takes off these lines
and this delivery fee.

Both are asked twice for every order. Once at the form, so the customer sees
the new total before pressing the button, and once more under the cart's lock
in ``create_order_from_cart``, from the locked lines. The second answer is the
one that is charged; the first is a preview (§9 Phase 16 item 4).

A code that cannot be used raises :class:`Refused`, which carries a reason
and the sentence the customer is shown. A code that does not exist, is
switched off, is outside its dates or is used up gets one and the same
sentence, so the form cannot be used to find out which codes exist.
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from product.templatetags.price_format import price

from .models import Order, PromoCode, SOLD

#: The least an order may cost after a code, in so'm. A code never makes an
#: order free, because no gateway can be asked for nothing: a discount that
#: would take the total below this is cut to leave it (§17 #318).
FLOOR = Decimal('1000')

#: Why a code was refused. The first is deliberately one answer for four
#: cases; the rest tell the customer something they can act on.
UNKNOWN = 'unknown'
MINIMUM = 'minimum'
USED = 'used'
UNPAID = 'unpaid'
NO_PRODUCT = 'no_product'
NOTHING_OFF = 'nothing_off'

MESSAGES = {
    UNKNOWN: _("Bunday promokod yoʻq yoki u hozir amal qilmaydi."),
    MINIMUM: _("Bu promokod mahsulotlar summasi %(sum)s soʻmdan boshlanganda amal qiladi."),
    USED: _("Siz bu promokoddan avval foydalangansiz."),
    UNPAID: _("Bu promokod bilan toʻlanmagan buyurtmangiz bor. "
               "Uni toʻlang yoki bekor qiling."),
    NO_PRODUCT: _("Savatingizda bu promokod amal qiladigan mahsulot yoʻq."),
    NOTHING_OFF: _("Bu promokod ushbu buyurtmada narxni kamaytirmaydi."),
}


class Refused(Exception):
    """A code that cannot be used on this order; carries why, in words."""

    def __init__(self, reason, **facts):
        super().__init__(reason)
        self.reason = reason
        self.facts = facts

    @property
    def message(self):
        """The sentence shown to the customer, in the page's language."""
        return MESSAGES[self.reason] % self.facts


@dataclass(frozen=True)
class Applied:
    """A code that may be used, and what it takes off this order."""
    promo: PromoCode
    discount: Decimal
    #: The product a product code was taken from; None for the other kinds.
    product: object = None


def spelling(text):
    """A typed code in the one spelling codes are kept in: no spaces, capitals."""
    return re.sub(r'\s+', '', str(text or '')).upper()


def find(text):
    """The code a customer typed, or None. Letter case and spaces do not matter."""
    code = spelling(text)
    if not PromoCode.CODE_RE.match(code):
        return None
    return PromoCode.objects.filter(code=code).first()


def check(promo, user, goods, now=None):
    """Raise :class:`Refused` unless ``user`` may use ``promo`` on these goods.

    ``goods`` is the sum of the lines before delivery, which is what a
    minimum is set against.

    A code that is once per customer is refused to a customer who has a paid
    order with it, and also to one who has an unpaid order with it. Counting
    paid orders alone would let somebody open several orders with the code
    first and pay for them all afterwards. The unpaid one can be paid or
    cancelled, and the sentence says so (§17 #343).
    """
    now = now or timezone.now()
    if (promo is None or not promo.is_active
            or (promo.starts_at and now < promo.starts_at)
            or (promo.ends_at and now > promo.ends_at)
            or (promo.max_uses is not None and promo.used_count >= promo.max_uses)):
        raise Refused(UNKNOWN)
    if goods < promo.min_subtotal:
        raise Refused(MINIMUM, sum=price(promo.min_subtotal))
    if promo.once_per_customer:
        mine = Order.objects.filter(user=user, promo=promo)
        if mine.filter(status__in=SOLD).exists():
            raise Refused(USED)
        if mine.filter(status=Order.Status.PAYING).exists():
            raise Refused(UNPAID)


def _share(amount, percent):
    """``percent`` per cent of ``amount``, rounded down to a whole so'm."""
    return Decimal(int(amount) * int(percent) // 100)


def discount(promo, lines, delivery):
    """What ``promo`` takes off these lines and this fee: ``(so'm, product)``.

    ``lines`` are cart lines; each has a unit price, a quantity and a variant.
    ``product`` is the product a product code was taken from, and None for a
    code that discounts the order.

    A product code discounts one item, and an item is one piece, not a line:
    the code comes off one shirt however many of it are in the cart. When
    several items could take it, the dearest does (§17 #317, #319).

    Raises :class:`Refused` when the cart holds none of a product code's
    products, and when the code would take nothing off at all: free delivery
    on an order whose delivery is already free, or a total already at the
    floor.
    """
    goods = sum(((line.price_stat or Decimal('0')) * line.quantity for line in lines),
                Decimal('0'))
    total = goods + delivery
    product = None
    Kind = PromoCode.Kind

    if promo.is_for_products:
        wanted = set(promo.products.values_list('pk', flat=True))
        covered = [line for line in lines if line.variant.product_id in wanted]
        if not covered:
            raise Refused(NO_PRODUCT)
        # The dearest one piece; the lowest id settles a tie, so the form and
        # the lock always pick the same line.
        line = max(covered, key=lambda it: (it.price_stat or Decimal('0'), -it.pk))
        unit = line.price_stat or Decimal('0')
        off = (_share(unit, promo.value) if promo.kind == Kind.PRODUCT_PERCENT
               else min(promo.value, unit))
        product = line.variant.product
    elif promo.kind == Kind.ORDER_PERCENT:
        off = _share(total, promo.value)
    elif promo.kind == Kind.ORDER_SUM:
        off = promo.value
    else:
        off = delivery

    off = min(Decimal(off), total - FLOOR)
    if off <= 0:
        raise Refused(NOTHING_OFF)
    return off, product


def apply(text, user, lines, delivery):
    """The typed code applied to this cart: an :class:`Applied`, or it raises.

    ``lines`` must have their variants loaded; the caller chooses how.
    """
    promo = find(text)
    goods = sum(((line.price_stat or Decimal('0')) * line.quantity for line in lines),
                Decimal('0'))
    check(promo, user, goods)
    off, product = discount(promo, lines, delivery)
    return Applied(promo=promo, discount=off, product=product)
