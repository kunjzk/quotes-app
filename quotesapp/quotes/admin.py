from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Source, Quote, EmailPreference, EmailSend
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


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "kind", "collection", "created_at")
    list_filter = ("kind",)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "source", "user", "page_number", "timestamp_seconds", "created_at", "deleted_at")
    search_fields = ("quote",)
    list_filter = ("source", "user")
    
    def get_queryset(self, request):
        return Quote.all_objects.all()


@admin.register(EmailPreference)
class EmailPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "timezone", "send_hour", "send_minute", "unsubscribed_at")
    list_filter = ("enabled", "timezone")


@admin.register(EmailSend)
class EmailSendAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "sent_at")
    list_filter = ("date",)
