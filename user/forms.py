"""Account forms: the phone number that starts a code, the code, the name."""
from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from .models import User, normalize_uz_phone, phone_regex


class PhoneForm(forms.Form):
    """The one field sign-in asks for."""
    phone = forms.CharField(
        max_length=20,
        error_messages={'required': _("Telefon raqamni kiriting.")},
    )

    def clean_phone(self):
        """Normalise, then validate, so every later lookup sees one form of it.

        Digits from other scripts are refused first. The pattern takes them
        for digits, so the same number written in them would be a second
        account, with counters of its own for how many codes it may be sent.
        """
        value = self.cleaned_data['phone']
        if any(ch.isdigit() and not ch.isascii() for ch in value):
            raise forms.ValidationError(phone_regex.message)
        value = normalize_uz_phone(value)
        phone_regex(value)
        return value


class SignupForm(PhoneForm):
    """Sign-up: the number, and consent to the two documents."""
    # Required here as well as in the browser: the `required` attribute is a
    # convenience, and a POST does not have to come from our page. An account
    # is only created with the consent the privacy policy says it rests on
    # (§17 #291).
    agree = forms.BooleanField(error_messages={
        'required': _("Hisob yaratish uchun foydalanish shartlari va maxfiylik "
                      "siyosatiga rozilik bering."),
    })


class OTPForm(forms.Form):
    """Six-digit code entry."""
    code = forms.CharField(
        validators=[RegexValidator(regex=r'^\d{6}$', message=_("6 ta raqam kiriting."))],
        error_messages={'required': _("Kodni kiriting.")},
    )


class ProfileForm(forms.ModelForm):
    """The name, which is all a customer can change about their account."""
    class Meta:
        model = User
        fields = ('first_name',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = False
        self.fields['first_name'].label = _("Ism")
