"""Template helpers for the legal pages and the contact details.

    {% load legal_tags %}
    {% get_legal as legal %}
    {{ legal.seller.phone }} · {{ legal.refund_days }} {{ legal.refund_days|ru_plural:"день,дня,дней" }}

A simple tag rather than a context processor, on purpose: the footer prints the
contact details, and Django can render an error page without running any
context processor at all (§17 #66). A tag asks for the facts itself, so the
phone number in the footer is right on the page where it matters most.
"""
from django import template

from core import legal

register = template.Library()


@register.simple_tag
def get_legal():
    """The shop's legal facts - see :func:`core.legal.facts`."""
    return legal.facts()


@register.filter
def legal_date(value):
    """A document's date the way each language writes one in a heading.

    Django's own formats get two of the three wrong for this: the Uzbek one
    capitalises the month mid-sentence ("15-Sentabr, 2026-yil") where an Uzbek
    document writes "2026-yil 15-sentabr", and the English one abbreviates
    ("Sept. 15, 2026"). The month names still come from Django's catalogues;
    only the order and the case are ours.
    """
    from django.utils import translation
    from django.utils.dates import MONTHS, MONTHS_ALT
    if not value:
        return ''
    lang = (translation.get_language() or 'uz')[:2]
    if lang == 'uz':
        return f'{value.year}-yil {value.day}-{str(MONTHS[value.month]).lower()}'
    if lang == 'ru':
        return f'{value.day} {MONTHS_ALT[value.month]} {value.year} г.'
    return f'{value.day} {MONTHS[value.month]} {value.year}'


#: WORD JOINER - invisible, and forbids a line break on either side of it.
_JOIN = '\u2060'


@register.filter
def legal_range(low, high):
    """``low–high`` as one value that never breaks: ``{{ a|legal_range:b }}``.

    A range is read as one figure, but the en dash is a break opportunity, and
    at 390 px the terms put "1–" at the end of one line and "6 kunda" at the
    start of the next (§17 #204).
    """
    return f'{low}{_JOIN}–{_JOIN}{high}'


@register.filter
def ru_plural(value, forms):
    """The Russian noun form a number takes: ``"день,дня,дней"``.

    Russian agrees a noun with the number before it in three ways, and the
    legal pages print their figures from ``core.legal`` rather than as copy -
    so the word has to follow the number when the number changes. English uses
    Django's ``pluralize``; Uzbek does not inflect after a numeral at all.
    """
    one, few, many = forms.split(',')
    try:
        n = abs(int(value))
    except (TypeError, ValueError):
        return many
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
