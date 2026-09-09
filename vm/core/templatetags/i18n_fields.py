"""Template filter for per-row translated model fields.

    {% load i18n_fields %}
    {{ product|t:"name" }}
"""
from django import template

from core.i18n import tfield

register = template.Library()


@register.filter(name='t')
def translated_field(obj, field):
    """Return the active language's version of ``field`` on ``obj``."""
    return tfield(obj, field)
