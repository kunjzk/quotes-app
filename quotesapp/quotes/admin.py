from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Books, Quotes
from .forms import QuotesUserCreationForm, QuotesUserChangeForm


@admin.register(User)
class QuotesUserAdmin(UserAdmin):
    list_display = ("username", "email", "is_staff")
    form = QuotesUserChangeForm
    add_form = QuotesUserCreationForm
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "first_name", "last_name", "email", "password1", "password2"),
        }),
    )


@admin.register(Books)
class BooksAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at")


@admin.register(Quotes)
class QuotesAdmin(admin.ModelAdmin):
    list_display = ("quote", "book", "user", "page_number", "created_at")
    search_fields = ("quote",)
    list_filter = ("book", "user")
