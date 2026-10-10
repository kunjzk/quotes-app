from django import forms
from .models import User, Source, Quote, EmailPreference
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from quotes.mail import timezone_choices

class QuotesUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email
    
class QuotesUserChangeForm(UserChangeForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
    
    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

class QuoteCreateForm(forms.ModelForm):
    source = forms.ModelChoiceField(queryset=Source.objects.all(), required=False, label="Book")
    title = forms.CharField(required=False)
    creator = forms.CharField(required=False, label="Author")

    class Meta:
        model = Quote
        fields = ['quote', 'source', 'page_number']


class UserRegistrationForm(forms.ModelForm):
    """Simple registration form for new users - only first name, last name, email, password."""
    
    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8,
        label='Password',
        help_text='At least 8 characters'
    )
    
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label='Confirm password'
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        # Generate username from email
        user.username = self.cleaned_data['email'].split('@')[0].lower()
        # Handle duplicate usernames
        base_username = user.username
        counter = 1
        while User.objects.filter(username=user.username).exists():
            user.username = f"{base_username}{counter}"
            counter += 1
        
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class EmailPreferenceForm(forms.ModelForm):
    """Account page: whether, when, and in which zone to send today's letter."""

    class Meta:
        model = EmailPreference
        fields = ["enabled", "timezone", "send_hour", "send_minute"]
        labels = {
            "enabled": "Email me today's passages",
            "timezone": "Timezone",
            "send_hour": "Hour",
            "send_minute": "Minute",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = ""
        if self.instance and self.instance.timezone:
            current = self.instance.timezone
        self.fields["timezone"].widget = forms.Select(choices=timezone_choices(current))
        self.fields["send_hour"].widget = forms.Select(
            choices=[(hour, f"{hour:02d}") for hour in range(24)]
        )
        minute_choices = [(minute, f"{minute:02d}") for minute in (0, 15, 30, 45)]
        current_minute = getattr(self.instance, "send_minute", None)
        if current_minute not in (None, *[m for m, _ in minute_choices]):
            minute_choices.append((current_minute, f"{current_minute:02d}"))
            minute_choices.sort()
        self.fields["send_minute"].widget = forms.Select(choices=minute_choices)
        self.fields["enabled"].widget = forms.CheckboxInput()