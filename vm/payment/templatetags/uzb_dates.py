# payment/templatetags/date_extras.py
from django import template

register = template.Library()

UZ_MONTHS_FULL = ['', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
                  'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr']

UZ_MONTHS_SHORT = ['', 'Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyn',
                   'Iyl', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek']


@register.filter
def uz_date(value):
    if not value:
        return ''
    return f"{value.day:02d} {UZ_MONTHS_SHORT[value.month]} {value.year}"


@register.filter
def uz_date_full(value):
    if not value:
        return ''
    return f"{value.day:02d} {UZ_MONTHS_FULL[value.month]} {value.year}"