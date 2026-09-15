from quotes.models import Quote, Source, User, TodayPreference, TodaySelection
from django.db import transaction, DataError, IntegrityError, DatabaseError
from django.db.models import Count, Q, QuerySet
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging
import math
import random

logger = logging.getLogger(__name__)

class QuoteCreationResult:
    def __init__(self, quote: Quote, status: str, existing_quote_id: int|None, error_message: str|None):
        self.quote = quote
        self.existing_quote_id = existing_quote_id
        self.error_message = error_message
        try:
            self.status = self.validate_status(status, existing_quote_id, error_message)
        except ValueError as e:
            raise ValueError(f"Invalid status: {status}")
    
    def validate_status(self, status: str, existing_quote_id: int|None, error_message: str|None) -> str:
        if status not in ["success", "form_error", "quote_exists"]:
            raise ValueError(f"Invalid status: {status}")
        elif status == "quote_exists" and existing_quote_id is None:
            raise ValueError("Existing quote ID is required when status is quote_exists")
        elif status == "form_error" and error_message is None:
            raise ValueError("Error message is required when status is form_error")
        else:
            return status
    

def validate_quote_creation_input(quote_text: str, source: Source|None, title: str|None, creator: str|None, page_number: int|None) -> None:
    """
    Validate user input for creating a quote.
    If the source is not provided, then both the title and creator must be provided.
    If the source is provided, then the title and creator must not be provided.
    """
    if not source:
        if not (title and creator):
            raise ValueError("Please select a book or enter both a title and author.")
        if len(title) > 255:
            raise ValueError("Title must be less than 255 characters.")
        if len(creator) > 255:
            raise ValueError("Author must be less than 255 characters.")
    else:
        if title or creator:
            raise ValueError("You can only EITHER: 1) select a book OR 2) enter both a title and author.")
    
    if not quote_text:
        raise ValueError("Quote text is required.")
    
    if page_number and page_number < 0:
        raise ValueError("Page number must be greater than or equal to 0.")

def create_quote(quote_text: str, source: Source|None, title: str|None, creator: str|None, page_number: int|None, user: User) -> QuoteCreationResult:
    """
    Create a quote.
    If the quote validation fails, then the error message is returned.
    If the quote already exists, then the quote id of the existing quote is returned.
    If the quote does not exist, then the quote is created.
    """
    try:
        validate_quote_creation_input(quote_text, source, title, creator, page_number)
    except ValueError as e:
        return QuoteCreationResult(None, "form_error", None, str(e))
    
    with transaction.atomic():
        if not source:
            source, _ = Source.objects.get_or_create(
                    title=title,
                    creator=creator,
                )
        existing_quote = Quote.objects.filter(
            quote=quote_text,
            source=source,
            user=user,
        ).first()
        if existing_quote:
            return QuoteCreationResult(existing_quote, "quote_exists", existing_quote.id, None)
        else:
            quote = Quote(
                quote=quote_text,
                source=source,
                    user=user,
                    page_number=page_number
                )
            quote.save()
            return QuoteCreationResult(quote, "success", None, None)

def find_quotes_and_send_email(user_id: int) -> None:
    """
    Pick three random quotes from the user's quotes and send an email to the user.
    """
    user = User.objects.get(id=user_id)
    logger.info(f"Finding quotes and sending email to {user.email}")
    quotes = list(Quote.objects.filter(user=user).select_related('source').order_by('?')[:3])
    if not quotes:
        logger.info(f"No quotes found for user {user.email}, not sending email")
        return
    
    date = timezone.now().strftime("%Y-%m-%d")
    subject = f"{date}: Quotes from {_join_names([quote.source.creator for quote in quotes])}"
    message = ""
    message += f"Dear {user.first_name},\n\n"
    message += f"Here are three quotes from your collection. Hope you enjoy them!\n\n"
    for quote in quotes:
        message += f"{quote.quote}\n"
        message += f"{quote.source.title} - {quote.source.creator}\n"
        if quote.location_label:
            message += f"{quote.location_label}\n"
    message += "\n\nSee you tomorrow!\n\nBest regards,\nThe Quotes App"
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


def _join_names(names: list[str]) -> str:
    """"A", "A and B", "A, B and C", skipping blanks and repeats."""
    unique = list(dict.fromkeys(name for name in names if name))
    if not unique:
        return "your collection"
    if len(unique) == 1:
        return unique[0]
    return f"{', '.join(unique[:-1])} and {unique[-1]}"


# --- Today screen -----------------------------------------------------------

# A quote that has never been shown is weighted as though it was last shown
# this many days ago, so it is strongly (but not exclusively) preferred.
NEVER_SHOWN_DAYS = 365

# Values a user can type into a blank to mean "no filter".
ANY_VALUES = {"", "any", "anyone", "all"}


def normalize_criteria_value(value: str | None) -> str:
    value = (value or "").strip()
    if value.casefold() in ANY_VALUES:
        return ""
    return value[:255]


def get_today_preference(user: User) -> TodayPreference:
    preference, _ = TodayPreference.objects.get_or_create(user=user)
    return preference


def update_today_preference(user: User, quote_count: int, creator: str | None, source_title: str | None) -> TodayPreference:
    """Persist the user's Today criteria. Raises ValidationError on bad input."""
    preference = get_today_preference(user)
    preference.quote_count = quote_count
    preference.creator = normalize_criteria_value(creator)
    preference.source_title = normalize_criteria_value(source_title)
    preference.full_clean()
    preference.save()
    logger.info(
        "Today preference updated",
        extra={"user_id": user.id, "criteria": preference.criteria_key},
    )
    return preference


def _filter_field(queryset: QuerySet, field: str, value: str) -> QuerySet:
    """
    Case-insensitive exact match on `field`; if nothing matches exactly, fall
    back to a substring match so a partially typed value still narrows results.
    """
    value = (value or "").strip()
    if not value:
        return queryset
    exact = queryset.filter(**{f"{field}__iexact": value})
    if exact.exists():
        return exact
    return queryset.filter(**{f"{field}__icontains": value})


def filter_quotes_for_today(user: User, creator: str = "", source_title: str = "") -> QuerySet[Quote]:
    """Narrow the user's quotes to the chosen creator and/or source ("" means any)."""
    quotes = Quote.objects.filter(user=user).select_related("source")
    quotes = _filter_field(quotes, "source__creator", creator)
    quotes = _filter_field(quotes, "source__title", source_title)
    return quotes


def recency_weight(quote: Quote, now) -> float:
    """Higher for quotes never shown or shown long ago; 1 for quotes shown today."""
    if quote.last_shown_at is None:
        return NEVER_SHOWN_DAYS + 1
    days = max(0, (now - quote.last_shown_at).days)
    return min(days, NEVER_SHOWN_DAYS) + 1


def pick_quotes(candidates, count: int, now=None, rng=None) -> list[Quote]:
    """
    Weighted random sample without replacement (Efraimidis-Spirakis): each
    candidate gets key u^(1/weight) and the `count` largest keys win. Quotes
    that are new or stale therefore win far more often than recently shown ones.
    """
    if count <= 0:
        return []
    now = now or timezone.now()
    rng = rng or random
    keyed = [
        (math.pow(rng.random(), 1.0 / recency_weight(quote, now)), quote)
        for quote in candidates
    ]
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return [quote for _, quote in keyed[:count]]


def _ordered_by_ids(queryset: QuerySet[Quote], ids: list[int]) -> list[Quote]:
    by_id = queryset.in_bulk(ids)
    return [by_id[quote_id] for quote_id in ids if quote_id in by_id]


def get_todays_quotes(user: User, preference: TodayPreference | None = None, now=None, rng=None) -> list[Quote]:
    """
    Quotes for the user's Today screen.

    The pick is made once per day per set of criteria and reused afterwards so
    the screen is stable across reloads. Whenever new quotes are picked their
    `last_shown_at` is stamped, which feeds the recency bias on later days.
    """
    now = now or timezone.now()
    today = timezone.localdate(now)
    preference = preference or get_today_preference(user)
    candidates = filter_quotes_for_today(user, preference.creator, preference.source_title)

    selection = TodaySelection.objects.filter(user=user).first()
    cache_hit = (
        selection is not None
        and selection.date == today
        and selection.criteria_key == preference.criteria_key
    )
    picked = _ordered_by_ids(candidates, selection.quote_ids) if cache_hit else []

    # Top up when this is a fresh pick, or when cached quotes have since been
    # deleted / no longer match.
    missing = preference.quote_count - len(picked)
    extra = []
    if missing > 0:
        remaining = candidates.exclude(id__in=[quote.id for quote in picked])
        extra = pick_quotes(remaining, missing, now=now, rng=rng)
        if extra:
            Quote.objects.filter(id__in=[quote.id for quote in extra]).update(last_shown_at=now)
            for quote in extra:
                quote.last_shown_at = now
            picked.extend(extra)

    if not cache_hit or extra:
        TodaySelection.objects.update_or_create(
            user=user,
            defaults={
                "date": today,
                "criteria_key": preference.criteria_key,
                "quote_ids": [quote.id for quote in picked],
            },
        )
    return picked


def suggest_today_values(user: User, field: str, query: str = "", creator: str = "", source_title: str = "", limit: int = 8) -> list[str]:
    """
    Autocomplete values for the Today criteria blanks, drawn only from sources
    the user has quotes in. The other blank (if filled) narrows the results,
    e.g. choosing a creator only suggests that creator's sources.
    """
    sources = Source.objects.filter(quote__user=user, quote__deleted_at__isnull=True)
    query = (query or "").strip()

    if field == "creator":
        sources = _filter_field(sources, "title", normalize_criteria_value(source_title))
        values = sources.exclude(creator="").filter(creator__icontains=query).values_list("creator", flat=True)
        return list(values.order_by("creator").distinct()[:limit])

    if field == "source":
        sources = _filter_field(sources, "creator", normalize_criteria_value(creator))
        values = sources.filter(title__icontains=query).values_list("title", flat=True)
        return list(values.order_by("title").distinct()[:limit])

    raise ValueError(f"Unknown suggestion field: {field}")

def search_passages(user: User, query: str) -> QuerySet[Quote]:
    """The user's passages whose text, source title or creator contains `query`."""
    query = (query or "").strip()
    return (
        Quote.objects.filter(user=user)
        .filter(
            Q(quote__icontains=query)
            | Q(source__title__icontains=query)
            | Q(source__creator__icontains=query)
        )
        .select_related("source")
        .order_by("source__title", "page_number", "timestamp_seconds", "id")
    )


def sources_on_shelf(user: User) -> QuerySet[Source]:
    """Sources the user has live (not deleted) passages in, annotated with `quote_count`."""
    live = Q(quote__user=user, quote__deleted_at__isnull=True)
    return (
        Source.objects.filter(live)
        .annotate(quote_count=Count("quote", filter=live))
        .order_by("-quote_count", "title")
    )
