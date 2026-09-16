from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q, UniqueConstraint

from .source_kinds import DEFAULT_KIND, KIND_CHOICES, SourceKind, get_kind

# Create your models here.

class QuoteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class Quote(models.Model):
    quote = models.TextField()
    source = models.ForeignKey('Source', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Where in the source the passage is: a page for print, a position in the
    # audio (e.g. a song lyric at 2:31) for recordings.
    page_number = models.IntegerField(null=True, blank=True)
    timestamp_seconds = models.PositiveIntegerField(null=True, blank=True)
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
                fields=["quote", "user", "source"],
                condition=Q(deleted_at__isnull=True),
                name="unique_quote_per_user_per_source_when_not_deleted"
            )
        ]

    def __str__(self):
        return self.quote

    @property
    def location(self) -> str:
        """Compact position for margins and lists: "42" or "2:31"."""
        if self.page_number is not None:
            return str(self.page_number)
        if self.timestamp_seconds is not None:
            return format_timestamp(self.timestamp_seconds)
        return ""

    @property
    def location_label(self) -> str:
        """Position for running text: "p. 42" or "2:31"."""
        if self.page_number is not None:
            return f"p. {self.page_number}"
        return self.location

    @property
    def margin_label(self) -> str:
        """What the Today margin shows: the position, or the kind's marker."""
        return self.location_label or self.source.marker

    @property
    def is_long(self) -> bool:
        """Long passages and multi-line lyrics are set smaller so they fit."""
        return len(self.quote) > 120 or self.quote.count("\n") >= 3


def format_timestamp(seconds: int) -> str:
    """2:31 under an hour, 1:02:03 beyond."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class Source(models.Model):
    """Where a passage comes from: a book, a song, and more kinds in time."""
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=DEFAULT_KIND)
    title = models.CharField(max_length=255)
    # The author of a book; the artist, speaker or director for other kinds.
    creator = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # A title and creator can belong to both a book and a song:
            # Born to Run is a Springsteen memoir and a Springsteen song.
            UniqueConstraint(
                fields=["title", "creator", "kind"],
                name="unique_source_title_creator_kind"
            )
        ]

    def __str__(self):
        return f"{self.title} by {self.creator}"

    @property
    def kind_spec(self) -> SourceKind:
        """Everything that differs between kinds: labels, marker, line breaks."""
        return get_kind(self.kind)

    @property
    def marker(self) -> str:
        return self.kind_spec.marker

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

    Blank creator / source_title mean "any".
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
    creator = models.CharField(max_length=255, blank=True, default="")
    source_title = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def criteria_key(self) -> str:
        """Stable identifier for the current criteria, used to cache today's pick."""
        return f"{self.quote_count}|{self.creator.strip().casefold()}|{self.source_title.strip().casefold()}"

    def __str__(self):
        return (
            f"{self.user_id}: {self.quote_count} quotes by "
            f"{self.creator or 'any'} in {self.source_title or 'any'}"
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