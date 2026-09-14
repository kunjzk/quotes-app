from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q, UniqueConstraint

# Create your models here.

class QuoteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class Quote(models.Model):
    quote = models.TextField()
    book = models.ForeignKey('Book', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    page_number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    # When this quote was last surfaced on the Today screen. Used to bias
    # selection towards quotes that are new or haven't been seen in a while.
    last_shown_at = models.DateTimeField(null=True, blank=True)

    objects = QuoteManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["quote", "user", "book"],
                condition=Q(deleted_at__isnull=True),
                name="unique_quote_per_user_per_book_when_not_deleted"
            )
        ]

    def __str__(self):
        return self.quote

class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["title", "author"],
                name="unique_title_author"
            )
        ]

    def __str__(self):
        return f"{self.title} by {self.author}"

class User(AbstractUser):
    email = models.EmailField(unique=True, blank=False)
    first_name = models.CharField(max_length=255, blank=False)
    last_name = models.CharField(max_length=255, blank=False)

    def __str__(self):
        return f"{self.username} - {self.email}"


class TodayPreference(models.Model):
    """
    Per-user criteria for the Today screen:
    "I want to see __ quotes by ____ author in ____ book."

    Blank author / book_title mean "any".
    """
    DEFAULT_QUOTE_COUNT = 3
    MIN_QUOTE_COUNT = 1
    MAX_QUOTE_COUNT = 50

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="today_preference"
    )
    quote_count = models.PositiveSmallIntegerField(
        default=DEFAULT_QUOTE_COUNT,
        validators=[MinValueValidator(MIN_QUOTE_COUNT), MaxValueValidator(MAX_QUOTE_COUNT)],
    )
    author = models.CharField(max_length=255, blank=True, default="")
    book_title = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def criteria_key(self) -> str:
        """Stable identifier for the current criteria, used to cache today's pick."""
        return f"{self.quote_count}|{self.author.strip().casefold()}|{self.book_title.strip().casefold()}"

    def __str__(self):
        return (
            f"{self.user_id}: {self.quote_count} quotes by "
            f"{self.author or 'any'} in {self.book_title or 'any'}"
        )


class TodaySelection(models.Model):
    """
    The quotes picked for a user's Today screen. Kept for one user/day/criteria
    so the same quotes are shown throughout the day, even across reloads.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="today_selection"
    )
    date = models.DateField()
    criteria_key = models.CharField(max_length=600)
    quote_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} @ {self.date}: {self.quote_ids}"