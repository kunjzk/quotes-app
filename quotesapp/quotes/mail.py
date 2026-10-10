"""Daily email: today's passages, sent at the user's local time."""

from smtplib import SMTPException
from zoneinfo import ZoneInfo, available_timezones

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from quotes.models import EmailPreference, EmailSend, User
from quotes.services import _join_names, get_todays_quotes, user_timezone

import logging

logger = logging.getLogger(__name__)

UNSUBSCRIBE_SALT = "quotes.email.unsubscribe"
# Today can be set to 50; a letter that long is unreadable. The rest stay on the site.
EMAIL_QUOTE_CAP = 5

COMMON_TIMEZONES = [
    "UTC",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Africa/Johannesburg",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Bangkok",
    "Asia/Singapore",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Perth",
    "Australia/Sydney",
    "Pacific/Auckland",
]


def get_email_preference(user: User) -> EmailPreference:
    preference, _ = EmailPreference.objects.get_or_create(user=user)
    user.email_preference = preference
    return preference


def timezone_choices(current: str = "") -> list[tuple[str, str]]:
    names = list(COMMON_TIMEZONES)
    if current and current not in names and current in available_timezones():
        names.append(current)
    return [(name, name.replace("_", " ")) for name in names]


def absolute_url(path: str) -> str:
    return f"{settings.APP_URL.rstrip('/')}{path}"


def unsubscribe_token(user: User) -> str:
    return signing.dumps({"u": user.pk}, salt=UNSUBSCRIBE_SALT)


def user_from_unsubscribe_token(token: str) -> User:
    data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    return User.objects.get(pk=int(data["u"]))


def unsubscribe_user(user: User) -> EmailPreference:
    preference = get_email_preference(user)
    preference.enabled = False
    if preference.unsubscribed_at is None:
        preference.unsubscribed_at = timezone.now()
    preference.save(update_fields=["enabled", "unsubscribed_at", "updated_at"])
    logger.info("Unsubscribed from daily email", extra={"user_id": user.id})
    return preference


def _local_now(preference: EmailPreference, now):
    tz_name = preference.timezone if preference.timezone in available_timezones() else "UTC"
    return now.astimezone(ZoneInfo(tz_name))


def is_past_send_time(preference: EmailPreference, now=None) -> bool:
    """True once today's local clock has reached the user's send time."""
    now = now or timezone.now()
    local = _local_now(preference, now)
    send_at = local.replace(
        hour=preference.send_hour,
        minute=preference.send_minute,
        second=0,
        microsecond=0,
    )
    return local >= send_at


def already_sent_on(user: User, local_date) -> bool:
    return EmailSend.objects.filter(user=user, date=local_date).exists()


def users_due_for_email(now=None) -> list[User]:
    """Active users who want mail, whose local send time has passed, and who have not been mailed today."""
    now = now or timezone.now()
    due = []
    users = User.objects.filter(is_active=True).select_related("email_preference")
    for user in users:
        preference = get_email_preference(user)
        if not preference.enabled:
            continue
        if not is_past_send_time(preference, now):
            continue
        local_date = _local_now(preference, now).date()
        if already_sent_on(user, local_date):
            continue
        due.append(user)
    return due


def find_quotes_and_send_email(
    user_id: int, *, now=None, rng=None, preview: bool = False
) -> bool:
    """
    Email the user today's passages (the same pick as the Today screen).

    Returns True if a message was handed to the mail backend. Preview sends
    even when the daily letter is turned off, and does not count as today's send.
    """
    now = now or timezone.now()
    try:
        user = User.objects.select_related("email_preference").get(id=user_id)
    except User.DoesNotExist:
        logger.warning("Skipping email; user does not exist", extra={"user_id": user_id})
        return False

    if not user.is_active and not preview:
        logger.info("Skipping email; user is inactive", extra={"user_id": user.id})
        return False

    preference = get_email_preference(user)
    if not preference.enabled and not preview:
        logger.info("Skipping email; daily letter is off", extra={"user_id": user.id})
        return False

    local_date = timezone.localdate(now, timezone=user_timezone(user))
    if not preview and already_sent_on(user, local_date):
        logger.info("Skipping email; already sent today", extra={"user_id": user.id, "date": str(local_date)})
        return False

    quotes = get_todays_quotes(user, now=now, rng=rng)
    if not quotes:
        logger.info("Skipping email; no passages to send", extra={"user_id": user.id})
        return False

    mailed = quotes[:EMAIL_QUOTE_CAP]
    omitted = len(quotes) - len(mailed)
    context = {
        "user": user,
        "quotes": mailed,
        "omitted": omitted,
        "today_url": absolute_url(reverse("quotes:today")),
        "unsubscribe_url": absolute_url(
            reverse("quotes:email_unsubscribe", args=[unsubscribe_token(user)])
        ),
    }
    subject = f"{local_date.isoformat()}: Quotes from {_join_names([quote.source.creator for quote in mailed])}"
    text_body = render_to_string("quotes/email/today.txt", context)
    html_body = render_to_string("quotes/email/today.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    try:
        message.send()
    except SMTPException:
        logger.exception("SMTP failed sending daily email", extra={"user_id": user.id})
        raise

    if not preview:
        EmailSend.objects.get_or_create(
            user=user,
            date=local_date,
            defaults={"quote_ids": [quote.id for quote in quotes]},
        )
    logger.info(
        "Sent daily email",
        extra={"user_id": user.id, "preview": preview, "quote_count": len(mailed)},
    )
    return True
