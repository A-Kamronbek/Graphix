"""Dates in running text, written the way each language writes them.

    {% load date_tags %}
    {{ order.created_at|date:"j E Y"|month_case }}

Django's Uzbek month names are capitalised - "16 Sentabr 2026" - while Uzbek
writes a month in lower case mid-sentence, as the legal documents already do
through ``legal_date`` (§18 #38). Russian's names are lower case already and
English capitalises its months, so only Uzbek is touched. The Uzbek formats
used on the site contain no other letters, so lower-casing the whole string
changes the month and nothing else.
"""
from django import template
from django.template.defaultfilters import stringfilter
from django.utils.translation import get_language

register = template.Library()


@register.filter(is_safe=True)
@stringfilter
def month_case(text):
    """``text`` with the month in the case the reader's language writes it."""
    if (get_language() or '')[:2] == 'uz':
        return text.lower()
    return text
