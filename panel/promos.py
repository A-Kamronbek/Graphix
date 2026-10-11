"""The form the owner makes and edits a promo code with.

A code's rules live in ``payment/promos.py`` and its own checks in
``PromoCode.clean``. This is only the screen's side of it: reading a day
typed as dd/mm/yyyy, asking for products when the kind needs them, and saying
every refusal in the panel's own words.

Once a code exists its spelling and its kind are fixed. Orders freeze the
code's text and what it took off, so nothing breaks if they change, but a
code handed out as "10 % off" that later means "free delivery" is a promise
changed after it was made. Everything else can be edited: the value, the
products, every limit, and whether it is switched on.
"""
from datetime import datetime, time

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payment.models import PromoCode
from product.models import Product

#: The ways a typed day is read. Day first, as the owner writes one; the ISO
#: form is what the browser's own calendar hands over.
DAY_READ = ('%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d')


def shown(moment):
    """A stored moment as the day the panel shows for it: dd/mm/yyyy, or ''."""
    if not moment:
        return ''
    day = timezone.localtime(moment).date()
    return f'{day.day:02d}/{day.month:02d}/{day.year:04d}'


class DayField(forms.CharField):
    """A day typed as dd/mm/yyyy. Blank is allowed and means no limit."""

    def __init__(self, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('max_length', 10)
        super().__init__(**kwargs)

    def clean(self, value):
        text = super().clean(value)
        if not text:
            return None
        for pattern in DAY_READ:
            try:
                return datetime.strptime(text.strip(), pattern).date()
            except ValueError:
                continue
        raise forms.ValidationError(
            _('Sanani kk/oo/yyyy koʻrinishida kiriting, masalan 16/09/2026.'))


class PromoForm(forms.ModelForm):
    """One promo code: what it is, what it takes off, and its limits."""

    starts_on = DayField()
    ends_on = DayField()

    class Meta:
        model = PromoCode
        fields = ['code', 'kind', 'value', 'products', 'max_uses', 'min_subtotal',
                  'once_per_customer', 'note', 'is_active']
        error_messages = {
            'code': {'unique': _('Bunday promokod allaqachon bor.')},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Blank means "none" for both: free delivery has no value, and most
        # codes have no minimum. The model says what a kind needs.
        self.fields['value'].required = False
        self.fields['min_subtotal'].required = False
        self.fields['products'].queryset = Product.objects.order_by('name')
        # The panel speaks for itself; Django's own sentences are not ours.
        for field in self.fields.values():
            field.error_messages['required'] = _('Bu maydonni toʻldiring.')
            field.error_messages['invalid'] = _('Qiymatni tekshiring.')
        self.fields['products'].error_messages['invalid_choice'] = _('Bunday mahsulot yoʻq.')
        self.fields['kind'].error_messages['invalid_choice'] = _('Turini tanlang.')
        self.fields['max_uses'].error_messages['min_value'] = _('Notoʻgʻri son.')
        # A zero is how the row says "none". The form shows that as an empty
        # box, which is also how it is typed.
        for name in ('value', 'min_subtotal'):
            if not self.initial.get(name):
                self.initial[name] = None
        if self.instance.pk:
            # Fixed once the code exists; see the module's own note.
            self.fields['code'].disabled = True
            self.fields['kind'].disabled = True
            self.initial.setdefault('starts_on', shown(self.instance.starts_at))
            self.initial.setdefault('ends_on', shown(self.instance.ends_at))

    def clean_value(self):
        return self.cleaned_data.get('value') or 0

    def clean_min_subtotal(self):
        return self.cleaned_data.get('min_subtotal') or 0

    def clean(self):
        """The parts that depend on one another: the kind, products and days."""
        data = super().clean()
        kind = data.get('kind')
        if kind in PromoCode.PRODUCT_KINDS:
            if not data.get('products'):
                self.add_error('products', _('Kamida bitta mahsulotni tanlang.'))
        elif 'products' in data:
            # A code for the whole order discounts whatever is in it.
            data['products'] = Product.objects.none()

        starts, ends = data.get('starts_on'), data.get('ends_on')
        if starts and ends and ends < starts:
            self.add_error('ends_on', _('Tugash sanasi boshlanish sanasidan oldin '
                                        'boʻlishi mumkin emas.'))
        elif 'starts_on' in data and 'ends_on' in data:
            # A code runs from the first moment of its first day to the last
            # moment of its last, in the shop's own time.
            zone = timezone.get_current_timezone()
            self.instance.starts_at = (
                timezone.make_aware(datetime.combine(starts, time.min), zone)
                if starts else None)
            self.instance.ends_at = (
                timezone.make_aware(datetime.combine(ends, time.max), zone)
                if ends else None)
        return data
