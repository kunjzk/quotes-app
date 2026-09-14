import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from quotes.models import Book, Quote, TodayPreference, TodaySelection
from quotes.services import (
    filter_quotes_for_today,
    get_todays_quotes,
    pick_quotes,
    recency_weight,
    suggest_today_values,
    update_today_preference,
)

User = get_user_model()


class TodayTestMixin:
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reader", email="reader@example.com", password="pw"
        )
        self.other = User.objects.create_user(
            username="other", email="other@example.com", password="pw"
        )
        self.walden = Book.objects.create(title="Walden", author="Henry David Thoreau")
        self.civil = Book.objects.create(title="Civil Disobedience", author="Henry David Thoreau")
        self.dune = Book.objects.create(title="Dune", author="Frank Herbert")

        self.walden_quotes = [
            Quote.objects.create(user=self.user, book=self.walden, quote=f"Walden {i}")
            for i in range(4)
        ]
        self.civil_quotes = [
            Quote.objects.create(user=self.user, book=self.civil, quote=f"Civil {i}")
            for i in range(2)
        ]
        self.dune_quotes = [
            Quote.objects.create(user=self.user, book=self.dune, quote=f"Dune {i}")
            for i in range(3)
        ]
        # Another user's quote in a book the reader has never quoted.
        self.secret = Book.objects.create(title="Secret Book", author="Nobody Known")
        Quote.objects.create(user=self.other, book=self.secret, quote="Not yours")


class FilterQuotesTest(TodayTestMixin, TestCase):
    def test_any_returns_all_of_users_quotes(self):
        quotes = filter_quotes_for_today(self.user)
        self.assertEqual(quotes.count(), 9)
        self.assertFalse(quotes.filter(user=self.other).exists())

    def test_filter_by_author_is_case_insensitive(self):
        quotes = filter_quotes_for_today(self.user, author="henry david thoreau")
        self.assertEqual(quotes.count(), 6)
        self.assertTrue(all(q.book.author == "Henry David Thoreau" for q in quotes))

    def test_filter_by_book(self):
        quotes = filter_quotes_for_today(self.user, book_title="Dune")
        self.assertEqual(quotes.count(), 3)

    def test_filter_by_author_and_book(self):
        quotes = filter_quotes_for_today(self.user, author="Henry David Thoreau", book_title="Walden")
        self.assertEqual(quotes.count(), 4)

    def test_partial_value_falls_back_to_substring_match(self):
        quotes = filter_quotes_for_today(self.user, author="thoreau")
        self.assertEqual(quotes.count(), 6)

    def test_exact_match_wins_over_substring_match(self):
        Book.objects.create(title="Dune Messiah", author="Frank Herbert")
        messiah = Book.objects.get(title="Dune Messiah")
        Quote.objects.create(user=self.user, book=messiah, quote="Messiah 0")
        quotes = filter_quotes_for_today(self.user, book_title="dune")
        self.assertEqual(quotes.count(), 3)

    def test_no_match_returns_empty(self):
        self.assertEqual(filter_quotes_for_today(self.user, author="Nobody Known").count(), 0)


class PickQuotesTest(TodayTestMixin, TestCase):
    def test_never_shown_quotes_are_strongly_preferred(self):
        now = timezone.now()
        recent = self.walden_quotes[:2]
        for quote in recent:
            quote.last_shown_at = now
        never = self.walden_quotes[2:]

        rng = random.Random(42)
        recent_picks = 0
        for _ in range(200):
            picked = pick_quotes(recent + never, 1, now=now, rng=rng)
            if picked[0] in recent:
                recent_picks += 1
        # Never-shown quotes weigh 366 vs 1, so recently shown ones almost never win.
        self.assertLess(recent_picks, 10)

    def test_stale_quotes_preferred_over_fresh_ones(self):
        now = timezone.now()
        fresh, stale = self.dune_quotes[0], self.dune_quotes[1]
        fresh.last_shown_at = now - timedelta(days=1)
        stale.last_shown_at = now - timedelta(days=200)

        rng = random.Random(7)
        stale_picks = sum(
            1 for _ in range(300) if pick_quotes([fresh, stale], 1, now=now, rng=rng)[0] is stale
        )
        self.assertGreater(stale_picks, 250)

    def test_recency_weight(self):
        now = timezone.now()
        quote = self.dune_quotes[0]
        self.assertEqual(recency_weight(quote, now), 366)
        quote.last_shown_at = now
        self.assertEqual(recency_weight(quote, now), 1)
        quote.last_shown_at = now - timedelta(days=30)
        self.assertEqual(recency_weight(quote, now), 31)
        quote.last_shown_at = now - timedelta(days=5000)
        self.assertEqual(recency_weight(quote, now), 366)

    def test_returns_all_when_fewer_candidates_than_requested(self):
        picked = pick_quotes(self.civil_quotes, 5)
        self.assertEqual(set(picked), set(self.civil_quotes))

    def test_samples_without_replacement(self):
        picked = pick_quotes(self.walden_quotes, 3, rng=random.Random(1))
        self.assertEqual(len(picked), 3)
        self.assertEqual(len({q.id for q in picked}), 3)


class GetTodaysQuotesTest(TodayTestMixin, TestCase):
    def test_defaults_to_three_from_any_book(self):
        quotes = get_todays_quotes(self.user)
        self.assertEqual(len(quotes), 3)
        self.assertTrue(all(q.user_id == self.user.id for q in quotes))

    def test_respects_count_and_filters(self):
        preference = update_today_preference(self.user, 2, "Frank Herbert", "")
        quotes = get_todays_quotes(self.user, preference)
        self.assertEqual(len(quotes), 2)
        self.assertTrue(all(q.book == self.dune for q in quotes))

    def test_stamps_last_shown_at_on_picked_quotes(self):
        now = timezone.now()
        quotes = get_todays_quotes(self.user, now=now)
        for quote in quotes:
            quote.refresh_from_db()
            self.assertEqual(quote.last_shown_at, now)
        untouched = Quote.objects.filter(user=self.user, last_shown_at__isnull=True).count()
        self.assertEqual(untouched, 6)

    def test_same_quotes_throughout_the_day(self):
        now = timezone.now()
        first = get_todays_quotes(self.user, now=now)
        later = get_todays_quotes(self.user, now=now + timedelta(hours=5))
        self.assertEqual([q.id for q in first], [q.id for q in later])
        self.assertEqual(TodaySelection.objects.filter(user=self.user).count(), 1)

    def test_new_day_avoids_yesterdays_quotes(self):
        now = timezone.now()
        yesterday = get_todays_quotes(self.user, now=now)
        today = get_todays_quotes(self.user, now=now + timedelta(days=1), rng=random.Random(3))
        # 9 candidates, 3 shown yesterday (weight 2) vs 6 never shown (weight 366).
        self.assertFalse({q.id for q in yesterday} & {q.id for q in today})

    def test_changing_criteria_repicks(self):
        now = timezone.now()
        get_todays_quotes(self.user, now=now)
        preference = update_today_preference(self.user, 1, "", "Dune")
        quotes = get_todays_quotes(self.user, preference, now=now)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].book, self.dune)

    def test_tops_up_when_a_selected_quote_is_deleted(self):
        now = timezone.now()
        preference = update_today_preference(self.user, 2, "", "Walden")
        first = get_todays_quotes(self.user, preference, now=now)
        first[0].deleted_at = now
        first[0].save()

        again = get_todays_quotes(self.user, preference, now=now)
        self.assertEqual(len(again), 2)
        self.assertEqual(again[0].id, first[1].id)
        self.assertNotIn(first[0].id, [q.id for q in again])

    def test_fewer_matches_than_requested_shows_all_matches(self):
        preference = update_today_preference(self.user, 10, "", "Civil Disobedience")
        quotes = get_todays_quotes(self.user, preference)
        self.assertEqual(set(quotes), set(self.civil_quotes))

    def test_no_matches_returns_empty_list(self):
        preference = update_today_preference(self.user, 3, "Nobody Known", "")
        self.assertEqual(get_todays_quotes(self.user, preference), [])


class UpdateTodayPreferenceTest(TodayTestMixin, TestCase):
    def test_any_style_values_are_stored_as_blank(self):
        preference = update_today_preference(self.user, 4, " ANY ", "all")
        self.assertEqual(preference.quote_count, 4)
        self.assertEqual(preference.author, "")
        self.assertEqual(preference.book_title, "")

    def test_rejects_out_of_range_count(self):
        with self.assertRaises(ValidationError):
            update_today_preference(self.user, 0, "", "")
        with self.assertRaises(ValidationError):
            update_today_preference(self.user, TodayPreference.MAX_QUOTE_COUNT + 1, "", "")

    def test_criteria_key_is_case_insensitive(self):
        a = update_today_preference(self.user, 3, "Frank Herbert", "Dune").criteria_key
        b = update_today_preference(self.user, 3, "frank herbert", "dune").criteria_key
        self.assertEqual(a, b)


class SuggestTodayValuesTest(TodayTestMixin, TestCase):
    def test_authors_only_from_users_books(self):
        self.assertEqual(
            suggest_today_values(self.user, "author"),
            ["Frank Herbert", "Henry David Thoreau"],
        )

    def test_author_query_filters(self):
        self.assertEqual(suggest_today_values(self.user, "author", query="thor"), ["Henry David Thoreau"])

    def test_books_narrowed_by_chosen_author(self):
        self.assertEqual(
            suggest_today_values(self.user, "book", author="Henry David Thoreau"),
            ["Civil Disobedience", "Walden"],
        )
        self.assertEqual(suggest_today_values(self.user, "book", author="any"), ["Civil Disobedience", "Dune", "Walden"])

    def test_authors_narrowed_by_chosen_book(self):
        self.assertEqual(suggest_today_values(self.user, "author", book_title="Dune"), ["Frank Herbert"])

    def test_soft_deleted_quotes_do_not_surface_books(self):
        for quote in self.dune_quotes:
            quote.deleted_at = timezone.now()
            quote.save()
        self.assertNotIn("Dune", suggest_today_values(self.user, "book"))

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            suggest_today_values(self.user, "publisher")


class TodayViewTest(TodayTestMixin, TestCase):
    def test_requires_login(self):
        resp = self.client.get(reverse("quotes:today"))
        self.assertEqual(resp.status_code, 302)

    def test_shows_three_quotes_by_default_with_criteria_sentence(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["quotes"]), 3)
        self.assertContains(resp, "search criteria")
        self.assertContains(resp, 'id="criteria-count"')
        self.assertContains(resp, "9 passages")
        self.assertTrue(TodayPreference.objects.filter(user=self.user).exists())

    def test_shows_filtered_quotes(self):
        update_today_preference(self.user, 5, "Frank Herbert", "")
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today"))
        self.assertEqual(len(resp.context["quotes"]), 3)
        self.assertEqual(resp.context["matching_quotes"], 3)
        self.assertTrue(resp.context["is_filtered"])
        self.assertContains(resp, "showing 3 of 9 passages")

    def test_no_match_state_keeps_criteria_editable(self):
        update_today_preference(self.user, 3, "Nobody Known", "")
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No passages match these criteria.")
        self.assertContains(resp, 'id="criteria-form"')

    def test_empty_library_shows_capture_prompt(self):
        Quote.objects.filter(user=self.user).update(deleted_at=timezone.now())
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today"))
        self.assertContains(resp, "Capture your first quote")
        self.assertNotContains(resp, 'id="criteria-form"')


class TodayPreferenceViewTest(TodayTestMixin, TestCase):
    def test_saves_preferences(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.post(
            reverse("quotes:today_preferences"),
            {"quote_count": "5", "author": "Frank Herbert", "book": "any"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(),
            {"success": True, "quote_count": 5, "author": "Frank Herbert", "book": ""},
        )
        preference = TodayPreference.objects.get(user=self.user)
        self.assertEqual(preference.quote_count, 5)
        self.assertEqual(preference.author, "Frank Herbert")
        self.assertEqual(preference.book_title, "")

    def test_rejects_non_numeric_count(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.post(reverse("quotes:today_preferences"), {"quote_count": "lots"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("whole number", resp.json()["error"])

    def test_rejects_out_of_range_count(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.post(reverse("quotes:today_preferences"), {"quote_count": "0"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_requires_login(self):
        resp = self.client.post(reverse("quotes:today_preferences"), {"quote_count": "3"})
        self.assertEqual(resp.status_code, 302)


class TodaySuggestViewTest(TodayTestMixin, TestCase):
    def test_author_suggestions(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today_suggest"), {"field": "author", "q": "her"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"suggestions": ["Frank Herbert"]})

    def test_book_suggestions_scoped_to_author(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(
            reverse("quotes:today_suggest"),
            {"field": "book", "q": "", "author": "Henry David Thoreau"},
        )
        self.assertEqual(resp.json(), {"suggestions": ["Civil Disobedience", "Walden"]})

    def test_never_suggests_other_users_books(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today_suggest"), {"field": "book", "q": "secret"})
        self.assertEqual(resp.json(), {"suggestions": []})

    def test_invalid_field(self):
        assert self.client.login(username="reader", password="pw")
        resp = self.client.get(reverse("quotes:today_suggest"), {"field": "publisher"})
        self.assertEqual(resp.status_code, 400)
