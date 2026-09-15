"""The facts the legal pages state, written once.

Everything a legal document says that is a *fact about the shop* rather than
wording lives here: who the seller is, how much is kept when a parcel comes
back uncollected, how long a refund takes, how long each kind of data is kept.
The three documents are written out in three languages each, so a figure typed
into the copy would be a figure typed nine times - and a number written down
twice is a number that will eventually disagree with itself (§17 #111).

Where a fact already lives in the code - the OTP window, the review photo
limit, the guest-cart age, a cookie's lifetime - it is read from there rather
than restated, so the privacy policy cannot promise one thing while the code
does another.

None of this is a panel setting, on purpose. Changing one of these values
changes terms a customer has already agreed to. That is an amendment: it lands
with a new entry in ``VERSIONS``, dated, in the same commit, so a customer can
see what changed and when (plan §9 Phase 8 item 4).
"""
import re
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from django.conf import settings
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

#: The seller as registered. GRAPHIX is the name the shop uses everywhere; the
#: registered name is what makes the public offer say who it is from, which the
#: E-commerce Law requires of an offer. Kamronbek's call (§17 #184): name,
#: address and contacts only - no tax number and no bank details on a public
#: page. The registration record's postal index (700000) is left out: that was
#: Tashkent's index in Soviet times and cannot be Qoʻqon's (§19 Q28). The legal
#: form is not stated until it is confirmed (§19 Q27).
SELLER = {
    'brand': 'GRAPHIX',
    'site': 'graphix.uz',
    'registered_name': 'Boboyev Abdurahmon Furqat oʻgʻli',
    'address': 'Fargʻona viloyati, Qoʻqon shahri, Sharq dahasi, 5-uy, 27-xonadon',
    'phone': '+998 50 788 84 36',
    'email': 'abdurahmonboboyev.magic@gmail.com',
    'telegram': 'greatestamal',
}

#: So'm kept when a parcel comes back to us uncollected or refused; the rest of
#: the payment is refunded by the admin. Kamronbek, answering §19 Q11 on
#: 2026-09-15 - "can be changed later", which is what a new version is for.
UNCOLLECTED_FEE = 15_000

#: Days to return money once the reason for a refund exists: the parcel is back
#: with us, a paid order was cancelled before it left, or a return was accepted.
REFUND_DAYS = 10

#: Days to answer a customer's complaint before it can become a dispute.
CLAIM_RESPONSE_DAYS = 10

#: Consumer Protection Law, art. 18: goods of proper quality may be exchanged
#: within ten days.
EXCHANGE_DAYS = 10

#: Art. 13: with no warranty period set, a defect may be claimed within six
#: months. Art. 14: a replacement is due within seven days of the claim.
DEFECT_CLAIM_MONTHS = 6
DEFECT_REPLACE_DAYS = 7

#: Uzpost's own figures (§19 Q10): 1-6 days anywhere in Uzbekistan.
TRANSIT_DAYS = (1, 6)

#: How long a branch holds a parcel for collection: 14 days on Bir Qadam, a
#: month for an ordinary parcel under the Postal Service Rules (§17 #103,
#: #186). The pages give the range rather than promising the longer one.
BRANCH_HOLD_DAYS = (14, 30)

#: The E-commerce Law's delivery term when none was agreed.
DELIVERY_DEADLINE_DAYS = 30

#: Measurements are taken by hand from the garment.
SIZE_TOLERANCE_CM = 1

#: Personal Data Law: how quickly a data subject's request is answered, and a
#: wrong record corrected.
DATA_REQUEST_DAYS = 10
DATA_CORRECTION_DAYS = 3

#: Who the site is for; a younger customer needs a parent's consent.
MINIMUM_AGE = 18


@dataclass(frozen=True)
class Version:
    """One published wording of a document.

    The number and the day it took effect, and what changed - in words a
    customer can read, so it is translated like any other copy.
    """
    number: str
    effective: date
    summary: object


#: Newest first. Amending a document means adding a row here in the same commit
#: as the new wording, never editing an old row: the history is the record of
#: what a customer was shown on a given day.
VERSIONS = {
    'terms': (
        Version('1.0', date(2026, 9, 15),
                _('Birinchi toʻliq tahrir: ommaviy oferta, toʻlov, yetkazib berish, '
                  'olib ketilmagan joʻnatmalar, qaytarish, sharhlar va sotuvchi '
                  'maʼlumotlari.')),
    ),
    'privacy': (
        Version('1.0', date(2026, 9, 15),
                _('Birinchi tahrir.')),
    ),
    'delivery': (
        Version('1.0', date(2026, 9, 15),
                _('Birinchi sanali tahrir: muddatlar, pochta boʻlimida saqlash, '
                  'olib ketilmagan joʻnatma va almashtirish tartibi.')),
    ),
}

#: The page title of each document, in the reader's language.
TITLES = {
    'terms': _('Foydalanish shartlari'),
    'privacy': _('Maxfiylik siyosati'),
    'delivery': _('Yetkazib berish va qaytarish'),
}


def document(key):
    """The current version of document ``key`` and its whole history."""
    history = VERSIONS[key]
    return {'version': history[0], 'history': history}


_SECTION = re.compile(r'<section\b[^>]*\bid="([^"]+)"[^>]*>\s*<h2\b[^>]*>(.*?)</h2>', re.S)


def contents(html):
    """The (id, heading) of every section in a rendered document, in order.

    The contents list is built from the text itself rather than written out
    beside it, so it cannot name a section the document does not have - and the
    three languages of one document can be checked against each other.
    """
    return [(anchor, strip_tags(title).strip()) for anchor, title in _SECTION.findall(html)]


def facts():
    """Every figure the legal pages print, read from where it lives.

    Built per call rather than at import: several of these sit in modules that
    import models, and a test may override a setting.
    """
    from cart.services import GUEST_CART_DAYS
    from core.ratelimit import MAX_WINDOW
    from product.images import MAX_BYTES
    from product.views import MAX_PHOTOS, MAX_TEXT
    from user import otp

    day = 24 * 60 * 60
    digits = ''.join(ch for ch in SELLER['phone'] if ch.isdigit())
    return SimpleNamespace(
        seller=SimpleNamespace(
            **SELLER,
            phone_href='+' + digits,
            telegram_url='https://t.me/' + SELLER['telegram'],
            site_url='https://' + SELLER['site'],
        ),
        uncollected_fee=UNCOLLECTED_FEE,
        refund_days=REFUND_DAYS,
        claim_days=CLAIM_RESPONSE_DAYS,
        exchange_days=EXCHANGE_DAYS,
        defect_claim_months=DEFECT_CLAIM_MONTHS,
        defect_replace_days=DEFECT_REPLACE_DAYS,
        transit_min=TRANSIT_DAYS[0],
        transit_max=TRANSIT_DAYS[1],
        hold_min=BRANCH_HOLD_DAYS[0],
        hold_max=BRANCH_HOLD_DAYS[1],
        delivery_deadline_days=DELIVERY_DEADLINE_DAYS,
        size_tolerance_cm=SIZE_TOLERANCE_CM,
        data_request_days=DATA_REQUEST_DAYS,
        data_correction_days=DATA_CORRECTION_DAYS,
        # Kept in settings, where the log handler reads it (§17 #196).
        log_days=settings.LOG_RETENTION_DAYS,
        minimum_age=MINIMUM_AGE,
        guest_cart_days=GUEST_CART_DAYS,
        rate_limit_minutes=MAX_WINDOW // 60,
        otp_minutes=otp.TTL_SECONDS // 60,
        otp_attempts=otp.MAX_ATTEMPTS,
        review_photos=MAX_PHOTOS,
        review_text=MAX_TEXT,
        review_photo_mb=MAX_BYTES // (1024 * 1024),
        session_days=settings.SESSION_COOKIE_AGE // day,
        language_cookie_days=settings.LANGUAGE_COOKIE_AGE // day,
        csrf_cookie_days=settings.CSRF_COOKIE_AGE // day,
    )
