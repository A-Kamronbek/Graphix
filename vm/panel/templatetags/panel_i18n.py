"""The sentences `panel.js` can show a person, in the reader's language.

§4 says no hardcoded user-facing strings, and a string typed into a .js file
cannot go through gettext — the file is served by the static handler and never
sees a request, let alone a language. The panel had eight of them: "Saqlanmadi",
"Yuklanmadi", the four upload refusals and two more.

So they are written here, in Python, where `{% trans %}`'s own catalogue can
reach them, and handed to the script as one JSON block that `json_script`
escapes. `{n}` and `{name}` are filled in by the script; gettext keeps them
because they are not `%`-format and `makemessages` has nothing to rewrite.
"""
from django import template
from django.utils.translation import gettext as _

register = template.Library()


@register.simple_tag
def panel_strings():
    """Return the dictionary `panel.js` reads out of `#pnl-i18n`."""
    return {
        'failed': _('Saqlanmadi'),
        'upload': _('Yuklanmadi'),
        'remove': _('Oʻchirish'),
        'tooMany': _('Koʻpi bilan {n} ta rasm.'),
        'tooBig': _('“{name}” juda katta.'),
        'badType': _('“{name}” — qoʻllab-quvvatlanmaydigan tur.'),
        'tooManyPixels': _('“{name}” — rasm oʻlchami juda katta.'),
        'notAnImage': _('“{name}” — rasm sifatida oʻqib boʻlmadi.'),
        'confirmDelete': _('“{name}” oʻchirilsinmi?'),
        'noFile': _('Tanlanmagan'),
    }
