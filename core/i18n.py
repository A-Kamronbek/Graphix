"""Per-row translation for model content.

Interface strings go through ``gettext`` and live in ``.po`` files. *Content* —
product names, descriptions, category and colour names — is per-row data typed by
the owner in the admin, so it lives in extra columns on the model instead:
``name`` (Uzbek, the source of truth), ``name_ru``, ``name_en``.

Uzbek stays in the **base** field rather than a ``name_uz`` column, so every row
that already exists keeps working with no backfill (§17 #8).

Usage:

* Python — ``tfield(product, "name")``
* Template — ``{{ product|t:"name" }}`` (see ``core/templatetags/i18n_fields.py``)
"""
from django.utils.translation import get_language


def tfield(obj, field):
    """Return ``obj.<field>_<active language>``, falling back to the base field.

    The fallback is deliberate and layered: an empty translation is as useless as
    a missing one, so a blank ``name_ru`` falls back to the Uzbek ``name`` rather
    than rendering an empty product title. Uzbek — and any language without its
    own column — reads the base field directly.
    """
    if obj is None:
        return ''

    lang = (get_language() or 'uz').split('-')[0]
    if lang != 'uz':
        value = getattr(obj, f'{field}_{lang}', None)
        if value:
            return value

    return getattr(obj, field, '') or ''
