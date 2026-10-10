from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from quotes.mail import (
    EMAIL_QUOTE_CAP,
    find_quotes_and_send_email,
    get_email_preference,
    unsubscribe_token,
    users_due_for_email,
)
from quotes.models import EmailPreference, EmailSend, Quote, Source, TodaySelection
from quotes.services import get_todays_quotes, update_today_preference
from quotes.tasks import create_email_tasks

User = get_user_model()


class EmailTestMixin:
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="pw",
            first_name="Ada",
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="pw", first_name="Bob"
        )
        self.walden = Source.objects.create(title="Walden", creator="Henry David Thoreau")
        self.dune = Source.objects.create(title="Dune", creator="Frank Herbert")
        self.quotes = [
            Quote.objects.create(user=self.user, source=self.walden, quote=f"Walden {i}", page_number=10 + i)
            for i in range(4)
        ]
        self.dune_quote = Quote.objects.create(
            user=self.user, source=self.dune, quote="Fear is the mind-killer.", page_number=8
        )
        Quote.objects.create(user=self.other, source=self.dune, quote="Not yours")
        self.client.login(username="reader", password="pw")
        self.now = datetime(2026, 10, 10, 7, 31, tzinfo=ZoneInfo("UTC"))


class SendEmailTest(EmailTestMixin, TestCase):
    def test_uses_the_same_passages_as_today(self):
        picked = get_todays_quotes(self.user, now=self.now)
        self.assertTrue(find_quotes_and_send_email(self.user.id, now=self.now))
        body = mail.outbox[0].body
        html = mail.outbox[0].alternatives[0][0]
        for quote in picked:
            self.assertIn(quote.quote, body)
            self.assertIn(quote.quote, html)
        again = get_todays_quotes(self.user, now=self.now)
        self.assertEqual([quote.id for quote in again], [quote.id for quote in picked])

    def test_respects_today_filters_and_count(self):
        update_today_preference(self.user, 2, "Frank Herbert", "")
        self.assertTrue(find_quotes_and_send_email(self.user.id, now=self.now))
        body = mail.outbox[0].body
        self.assertIn("Fear is the mind-killer.", body)
        self.assertNotIn("Walden 0", body)
        self.assertTrue(mail.outbox[0].subject.endswith(": Quotes from Frank Herbert"))

    def test_html_and_text_include_location_and_brand(self):
        Quote.objects.filter(user=self.user).exclude(pk=self.dune_quote.pk).delete()
        find_quotes_and_send_email(self.user.id, now=self.now)
        body = mail.outbox[0].body
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Dune — Frank Herbert", body)
        self.assertIn("p. 8", body)
        self.assertIn("ReadReadRead", body)
        self.assertIn("Open in ReadReadRead", html)
        self.assertIn("p. 8", html)
        self.assertNotIn("The Quotes App", body)
        self.assertNotIn("None", body)

    def test_links_use_app_url(self):
        with override_settings(APP_URL="https://readreadread.xyz"):
            find_quotes_and_send_email(self.user.id, now=self.now)
        body = mail.outbox[0].body
        self.assertIn("https://readreadread.xyz/quotes/today/", body)
        self.assertIn("https://readreadread.xyz/quotes/email/unsubscribe/", body)

    def test_skips_inactive_users(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(find_quotes_and_send_email(self.user.id, now=self.now))
        self.assertEqual(mail.outbox, [])

    def test_skips_when_daily_letter_is_off(self):
        preference = get_email_preference(self.user)
        preference.enabled = False
        preference.save()
        self.assertFalse(find_quotes_and_send_email(self.user.id, now=self.now))
        self.assertEqual(mail.outbox, [])

    def test_preview_sends_even_when_disabled_and_does_not_count(self):
        preference = get_email_preference(self.user)
        preference.enabled = False
        preference.save()
        self.assertTrue(find_quotes_and_send_email(self.user.id, now=self.now, preview=True))
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(EmailSend.objects.filter(user=self.user).exists())

    def test_skips_users_with_no_passages(self):
        Quote.objects.filter(user=self.user).delete()
        self.assertFalse(find_quotes_and_send_email(self.user.id, now=self.now))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailSend.objects.filter(user=self.user).exists())

    def test_does_not_send_twice_on_the_same_local_day(self):
        self.assertTrue(find_quotes_and_send_email(self.user.id, now=self.now))
        self.assertFalse(find_quotes_and_send_email(self.user.id, now=self.now))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailSend.objects.filter(user=self.user).count(), 1)

    def test_caps_a_long_today_list(self):
        update_today_preference(self.user, 10, "", "")
        extra = Source.objects.create(title="Extra", creator="Anon")
        for i in range(8):
            Quote.objects.create(user=self.user, source=extra, quote=f"Extra {i}")
        find_quotes_and_send_email(self.user.id, now=self.now)
        body = mail.outbox[0].body
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("more in ReadReadRead", body)
        self.assertEqual(html.count("white-space:pre-wrap"), EMAIL_QUOTE_CAP)

    def test_missing_user_is_a_no_op(self):
        self.assertFalse(find_quotes_and_send_email(99999, now=self.now))
        self.assertEqual(mail.outbox, [])


class TimezoneEmailTest(EmailTestMixin, TestCase):
    def test_today_and_email_share_the_users_local_date(self):
        get_email_preference(self.user)
        self.user.email_preference.timezone = "Asia/Singapore"
        self.user.email_preference.save()
        # 7:31am in Singapore is still the previous evening in UTC.
        now = datetime(2026, 10, 10, 23, 31, tzinfo=ZoneInfo("UTC"))
        picked = get_todays_quotes(self.user, now=now)
        find_quotes_and_send_email(self.user.id, now=now)
        selection = TodaySelection.objects.get(user=self.user)
        send = EmailSend.objects.get(user=self.user)
        self.assertEqual(selection.date.isoformat(), "2026-10-11")
        self.assertEqual(send.date.isoformat(), "2026-10-11")
        self.assertTrue(mail.outbox[0].subject.startswith("2026-10-11:"))
        self.assertEqual([quote.id for quote in picked], send.quote_ids)


class ScheduleTest(EmailTestMixin, TestCase):
    def test_due_after_local_send_time(self):
        get_email_preference(self.user)
        due = users_due_for_email(now=self.now)
        self.assertIn(self.user, due)
        self.assertIn(self.other, due)

    def test_not_due_before_send_time(self):
        early = datetime(2026, 10, 10, 7, 0, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(users_due_for_email(now=early), [])

    def test_singapore_morning_is_due_while_utc_evening_is_previous_day(self):
        preference = get_email_preference(self.user)
        preference.timezone = "Asia/Singapore"
        preference.send_hour = 7
        preference.send_minute = 30
        preference.save()
        other = get_email_preference(self.other)
        other.send_hour = 23
        other.send_minute = 45
        other.save()
        now = datetime(2026, 10, 10, 23, 31, tzinfo=ZoneInfo("UTC"))
        due_ids = [user.id for user in users_due_for_email(now=now)]
        self.assertIn(self.user.id, due_ids)
        self.assertNotIn(self.other.id, due_ids)

    def test_disabled_and_inactive_are_not_due(self):
        preference = get_email_preference(self.user)
        preference.enabled = False
        preference.save()
        self.other.is_active = False
        self.other.save()
        self.assertEqual(users_due_for_email(now=self.now), [])

    def test_already_sent_is_not_due(self):
        EmailSend.objects.create(user=self.user, date=self.now.date(), quote_ids=[])
        due_ids = [user.id for user in users_due_for_email(now=self.now)]
        self.assertNotIn(self.user.id, due_ids)

    @patch("quotes.tasks.send_email_task.delay")
    def test_fanout_only_enqueues_due_users(self, delay):
        self.other.is_active = False
        self.other.save()
        with patch("quotes.mail.timezone.now", return_value=self.now):
            create_email_tasks()
        delay.assert_called_once_with(self.user.id)


class AccountViewTest(EmailTestMixin, TestCase):
    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("quotes:account"))
        self.assertEqual(resp.status_code, 302)

    def test_saves_preferences(self):
        resp = self.client.post(
            reverse("quotes:account"),
            {
                "enabled": "on",
                "timezone": "Asia/Singapore",
                "send_hour": "8",
                "send_minute": "15",
            },
            follow=True,
        )
        self.assertContains(resp, "Saved.")
        preference = EmailPreference.objects.get(user=self.user)
        self.assertTrue(preference.enabled)
        self.assertEqual(preference.timezone, "Asia/Singapore")
        self.assertEqual(preference.send_hour, 8)
        self.assertEqual(preference.send_minute, 15)
        self.assertIsNone(preference.unsubscribed_at)

    def test_turning_off_records_unsubscribed_at(self):
        self.client.post(
            reverse("quotes:account"),
            {"timezone": "UTC", "send_hour": "7", "send_minute": "30"},
        )
        preference = EmailPreference.objects.get(user=self.user)
        self.assertFalse(preference.enabled)
        self.assertIsNotNone(preference.unsubscribed_at)

    def test_preview_sends_mail(self):
        resp = self.client.post(
            reverse("quotes:account"),
            {"action": "preview"},
            follow=True,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resp, "A preview is on its way")
        self.assertFalse(EmailSend.objects.filter(user=self.user).exists())

    def test_preview_without_passages_explains_itself(self):
        Quote.objects.filter(user=self.user).delete()
        resp = self.client.post(
            reverse("quotes:account"),
            {"action": "preview"},
            follow=True,
        )
        self.assertContains(resp, "Nothing to send")
        self.assertEqual(mail.outbox, [])


class UnsubscribeViewTest(EmailTestMixin, TestCase):
    def test_signed_link_turns_the_letter_off(self):
        token = unsubscribe_token(self.user)
        resp = self.client.get(reverse("quotes:email_unsubscribe", args=[token]))
        self.assertContains(resp, "Unsubscribed")
        preference = EmailPreference.objects.get(user=self.user)
        self.assertFalse(preference.enabled)
        self.assertIsNotNone(preference.unsubscribed_at)

    def test_garbage_token_is_not_found(self):
        resp = self.client.get(reverse("quotes:email_unsubscribe", args=["not-a-token"]))
        self.assertEqual(resp.status_code, 404)


class CeleryScheduleTest(TestCase):
    def test_beat_runs_every_fifteen_minutes(self):
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE["create-email-tasks"]
        self.assertEqual(entry["task"], "quotes.tasks.create_email_tasks")
        self.assertEqual(entry["schedule"].minute, {0, 15, 30, 45})
