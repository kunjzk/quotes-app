from django import forms
from .models import User, Book, Quote
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

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
    book = forms.ModelChoiceField(queryset=Book.objects.all(), required=False)
    title = forms.CharField(required=False)
    author = forms.CharField(required=False)

    class Meta:
        model = Quote
        fields = ['quote', 'book', 'page_number']


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