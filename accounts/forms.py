from django import forms
from django.contrib.auth.password_validation import validate_password
from .models import User


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'contact_number',
                  'barangay', 'user_type']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ['first_name', 'last_name', 'email', 'barangay']:
            self.fields[name].required = True
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') and cleaned.get('password2'):
            if cleaned['password1'] != cleaned['password2']:
                self.add_error('password2', "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])  # hashed
        user.role = 'member'   # never from the form, so nobody can self-register as admin
        if commit:
            user.save()
        return user