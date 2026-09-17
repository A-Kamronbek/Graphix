"""What a form's native controls say, in the reader's language.

A browser checks `required`, `pattern` and `min` itself before a form is sent,
and says so in a bubble - in the language of the browser, not the page: an
Uzbek page in an English browser said "Please fill out this field." `forms.js`
replaces those sentences with these, which gettext can reach because they are
written here rather than in the script (§4, the reasoning `panel_i18n` gives).

`{n}` is filled in by the script, never by Python. gettext marks those
entries `python-brace-format` all the same, which is harmless and useful:
msgfmt then checks that every translation kept its `{n}`.
"""
from django import template
from django.utils.translation import gettext as _

register = template.Library()


@register.simple_tag
def form_messages():
    """Return the dictionary `forms.js` reads out of `#gx-forms`."""
    return {
        'required': _('Bu maydonni toʻldiring.'),
        'checkbox': _('Davom etish uchun belgilang.'),
        'radio': _('Variantlardan birini tanlang.'),
        'select': _('Roʻyxatdan tanlang.'),
        'file': _('Faylni tanlang.'),
        'pattern': _('Koʻrsatilgan koʻrinishda kiriting.'),
        'number': _('Son kiriting.'),
        'whole': _('Butun son kiriting.'),
        'min': _('Eng kichik qiymat — {n}.'),
        'max': _('Eng katta qiymat — {n}.'),
        'invalid': _('Qiymatni tekshiring.'),
        'noFile': _('Tanlanmagan'),
        'files': _('Tanlangan fayllar: {n}'),
    }
