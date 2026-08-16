from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.db.models import Q

class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="E-postadress",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'namn@exempel.se',
            'type': 'email',
            'autofocus': True
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
        login_input = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if login_input and password:
            User = get_user_model()
            user_obj = User.objects.filter(
                Q(email__iexact=login_input) | Q(username__iexact=login_input)
            ).first()

            if user_obj:
                self.cleaned_data['username'] = user_obj.username

        return super().clean()


class UserRegistrationForm(forms.Form):
    first_name = forms.CharField(
        label="Förnamn",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Förnamn'
        })
    )
    last_name = forms.CharField(
        label="Efternamn",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Efternamn'
        })
    )
    email = forms.EmailField(
        label="E-postadress",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'namn@exempel.se'
        })
    )
    password1 = forms.CharField(
        label="Lösenord",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Minst 8 tecken'
        })
    )
    password2 = forms.CharField(
        label="Bekräfta lösenord",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Upprepa lösenordet'
        })
    )
    invite_code = forms.CharField(
        label="Tipsgruppskod (Pool Code)",
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 't.ex. ENGINE8',
            'style': 'letter-spacing: 1.5px; font-weight: 700; color: #FBBF24;'
        })
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Det finns redan ett konto med denna e-postadress.")
        return email.lower()

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1', '')
        p2 = self.cleaned_data.get('password2', '')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Lösenorden matchar inte.")
        if len(p1) < 8:
            raise forms.ValidationError("Lösenordet måste vara minst 8 tecken.")
        return p2