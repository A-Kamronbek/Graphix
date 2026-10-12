"""A phone number as the fields that show +998 themselves want it.

Every phone field on the storefront has +998 written in its frame and takes
the nine digits after it (§17 #365, #367). What a field is filled with comes
in whatever form it was kept or typed in: "+998 90 123 45 67" from an order or
an account, "+998901234567" from a sign-in link, or half a number typed and
refused. The field shows the nine digits, so +998 never appears twice.
"""
from django import template

from user.models import normalize_uz_phone

register = template.Library()


@register.filter
def national(value):
    """The number after +998, spaced as it is kept; anything else as it came.

    A value that is not a whole Uzbek number is handed back untouched: it is
    what the visitor typed, and the form is showing it back to be put right.
    """
    if not value:
        return ''
    text = str(value)
    normal = normalize_uz_phone(text)
    return normal[len('+998 '):] if normal.startswith('+998 ') else text
