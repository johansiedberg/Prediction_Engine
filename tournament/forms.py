from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="E-post",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'namn@exempel.se'
        })
    )
    password = forms.CharField(
        label="Lösenord",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '••••••••'
        })
    )

    def clean(self):
        email = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if email and password:
            User = get_user_model()
            try:
                # Filtrera bort admin/staff-konton från den vanliga inloggningen
                user_obj = User.objects.filter(
                    email__iexact=email,
                    is_staff=False,
                    is_superuser=False
                ).first()

                if not user_obj:
                    raise User.DoesNotExist

                # Ersätt värdet internt med användarens faktiska username
                self.cleaned_data['username'] = user_obj.username
            except User.DoesNotExist:
                raise ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.username_field.verbose_name},
                )
        return super().clean()