from django import forms
from .models import User, Books, Quotes
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
    book = forms.ModelChoiceField(queryset=Books.objects.all(), required=False)
    title = forms.CharField(required=False)
    author = forms.CharField(required=False)

    class Meta:
        model = Quotes
        fields = ['quote', 'book', 'page_number']