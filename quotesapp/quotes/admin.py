from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Books, Quotes


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    pass


@admin.register(Books)
class BooksAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at")


@admin.register(Quotes)
class QuotesAdmin(admin.ModelAdmin):
    list_display = ("quote", "book", "user", "page_number", "created_at")
    search_fields = ("quote",)
    list_filter = ("book", "user")
