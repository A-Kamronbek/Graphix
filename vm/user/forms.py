from django import forms
from .models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import MinimumLengthValidator


# phone validation
# settings
# forget password

class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': "Username yoki parol noto'g'ri.",
        'inactive': "Bu akkaunt faol emas.",
    }


class SignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'phone')

    error_messages = {
        'password_mismatch': "Parollar mos kelmadi.",
    }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name', '')
        if commit:
            user.save()
            # NOTE: phone is not stored on the default User model.
            # When you add a UserProfile model, persist phone here:
            #   UserProfile.objects.create(user=user, phone=self.cleaned_data.get('phone',''))
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['username'].max_length = 50
        self.fields['username'].help_text = "Maximum 50ta belgi. Harflar, raqamlar va _"
        self.fields['username'].validators.append(
            RegexValidator(
                regex=r'^[A-Za-z0-9_]+$',
                message="Harflar, raqamlar va _  mumkin"
            )
        )


class CustomMinimumLengthValidator(MinimumLengthValidator):

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                "Parol 8 belgidan kam bo'lmasligi kerak.",
                code='password_too_short',
            )

    def get_help_text(self):
        return "Parol 8 belgidan kam bo'lmasligi kerak."