from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from quotes.models import Book, Quote

User = get_user_model()


class LibraryMixin:
    def setUp(self):
        self.user = User.objects.create_user(username="reader", email="reader@example.com", password="pw")
        self.other = User.objects.create_user(username="other", email="other@example.com", password="pw")
        self.walden = Book.objects.create(title="Walden", author="Henry David Thoreau")
        self.dune = Book.objects.create(title="Dune", author="Frank Herbert")
        self.secret = Book.objects.create(title="Secret Book", author="Nobody Known")

        self.walden_quotes = [
            Quote.objects.create(user=self.user, book=self.walden, quote=f"Simplify, simplify {i}", page_number=90 + i)
            for i in range(4)
        ]
        self.dune_quote = Quote.objects.create(user=self.user, book=self.dune, quote="Fear is the mind-killer.")
        Quote.objects.create(user=self.other, book=self.secret, quote="Simplify, but secretly")
        self.client.login(username="reader", password="pw")


class ShelfViewTest(LibraryMixin, TestCase):
    def test_counts_exclude_deleted_passages(self):
        Quote.objects.filter(pk=self.walden_quotes[0].pk).update(deleted_at=timezone.now())
        resp = self.client.get(reverse("quotes:shelf"))
        counts = {b["book"].title: b["book"].quote_count for b in resp.context["books"]}
        self.assertEqual(counts, {"Walden": 3, "Dune": 1})
        self.assertEqual(resp.context["total_passages"], 4)

    def test_books_with_only_deleted_passages_leave_the_shelf(self):
        Quote.objects.filter(pk=self.dune_quote.pk).update(deleted_at=timezone.now())
        resp = self.client.get(reverse("quotes:shelf"))
        self.assertEqual([b["book"].title for b in resp.context["books"]], ["Walden"])

    def test_spine_height_reflects_count(self):
        resp = self.client.get(reverse("quotes:shelf"))
        heights = {b["book"].title: b["height"] for b in resp.context["books"]}
        self.assertEqual(heights["Walden"], 320)
        self.assertLess(heights["Dune"], heights["Walden"])

    def test_fullest_book_is_open_by_default(self):
        resp = self.client.get(reverse("quotes:shelf"))
        self.assertEqual(resp.context["selected_book"], self.walden)
        self.assertContains(resp, f'id="q{self.walden_quotes[0].id}"')

    def test_book_param_opens_that_book(self):
        resp = self.client.get(reverse("quotes:shelf"), {"book": self.dune.id})
        self.assertEqual(resp.context["selected_book"], self.dune)
        self.assertContains(resp, f'id="q{self.dune_quote.id}"')

    def test_book_param_ignores_books_not_on_users_shelf(self):
        resp = self.client.get(reverse("quotes:shelf"), {"book": self.secret.id})
        self.assertEqual(resp.context["selected_book"], self.walden)

    def test_filter_partial_lists_only_users_matches(self):
        resp = self.client.get(reverse("quotes:shelf"), {"q": "simplify", "partial": "results"})
        self.assertTemplateUsed(resp, "quotes/partials/passage_results.html")
        self.assertTemplateNotUsed(resp, "base.html")
        self.assertEqual(len(resp.context["results"]), 4)
        self.assertEqual(resp.context["matching_book_ids"], [self.walden.id])
        self.assertNotContains(resp, "secretly")

    def test_delete_from_shelf_returns_to_the_book(self):
        quote = self.walden_quotes[1]
        next_url = f"{reverse('quotes:shelf')}?book={self.walden.id}"
        resp = self.client.post(reverse("quotes:quote_delete", args=[quote.id]), {"next": next_url})
        self.assertRedirects(resp, next_url, fetch_redirect_response=False)
        self.assertIsNotNone(Quote.all_objects.get(pk=quote.pk).deleted_at)

    def test_delete_ignores_offsite_next(self):
        quote = self.walden_quotes[1]
        resp = self.client.post(reverse("quotes:quote_delete", args=[quote.id]), {"next": "https://evil.example/"})
        self.assertRedirects(resp, reverse("quotes:quotes_list"), fetch_redirect_response=False)


class SearchViewTest(LibraryMixin, TestCase):
    def test_requires_two_characters(self):
        resp = self.client.get(reverse("quotes:search"), {"q": "s"})
        self.assertEqual(resp.json(), {"passages": [], "books": []})

    def test_matches_text_title_and_author_for_this_user_only(self):
        resp = self.client.get(reverse("quotes:search"), {"q": "simplify"})
        data = resp.json()
        self.assertEqual(len(data["passages"]), 4)
        self.assertTrue(all(p["book_id"] == self.walden.id for p in data["passages"]))
        self.assertEqual(data["books"], [])

        data = self.client.get(reverse("quotes:search"), {"q": "herbert"}).json()
        self.assertEqual([p["id"] for p in data["passages"]], [self.dune_quote.id])
        self.assertEqual(data["books"], [{"id": self.dune.id, "title": "Dune", "author": "Frank Herbert", "count": 1}])

    def test_excludes_deleted_passages(self):
        Quote.objects.filter(pk=self.dune_quote.pk).update(deleted_at=timezone.now())
        data = self.client.get(reverse("quotes:search"), {"q": "mind-killer"}).json()
        self.assertEqual(data, {"passages": [], "books": []})

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("quotes:search"), {"q": "simplify"})
        self.assertEqual(resp.status_code, 302)


class CaptureViewTest(LibraryMixin, TestCase):
    def post(self, content):
        return self.client.post(reverse("quotes:capture"), {"content": content})

    def test_existing_book_matched_case_insensitively_with_page(self):
        resp = self.post("Heaven is under our feet.\n— walden p. 283")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["book_title"], "Walden")
        quote = Quote.objects.get(pk=data["quote_id"])
        self.assertEqual((quote.book, quote.page_number, quote.user), (self.walden, 283, self.user))

    def test_new_book_with_author(self):
        data = self.post("It is a truth universally acknowledged.\n— Pride and Prejudice | Jane Austen | p. 1").json()
        quote = Quote.objects.get(pk=data["quote_id"])
        self.assertEqual((quote.book.title, quote.book.author, quote.page_number), ("Pride and Prejudice", "Jane Austen", 1))

    def test_new_book_without_author(self):
        data = self.post("A line.\n— Notebook").json()
        self.assertEqual(Quote.objects.get(pk=data["quote_id"]).book.author, "")

    def test_page_marker_needs_a_word_boundary(self):
        data = self.post("Up we go.\n— Look Up 42").json()
        quote = Quote.objects.get(pk=data["quote_id"])
        self.assertEqual((quote.book.title, quote.page_number), ("Look Up 42", None))

    def test_duplicate_reports_existing_quote(self):
        data = self.post(f"{self.dune_quote.quote}\n— Dune").json()
        self.assertEqual(data["quote_id"], self.dune_quote.id)
        self.assertEqual(data["message"], "Quote already exists")

    def test_missing_attribution_is_rejected(self):
        resp = self.post("No book here.")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())


class ChromeTest(LibraryMixin, TestCase):
    def test_nav_has_three_destinations_and_account_menu(self):
        resp = self.client.get(reverse("quotes:shelf"))
        self.assertContains(resp, 'class="nav"')
        self.assertContains(resp, 'id="palette"')
        self.assertNotContains(resp, "cdn.tailwindcss.com")
        self.assertNotContains(resp, "unpkg.com")
        self.assertNotContains(resp, reverse("admin:index"))

    def test_admin_link_only_for_staff(self):
        self.user.is_staff = True
        self.user.save()
        resp = self.client.get(reverse("quotes:shelf"))
        self.assertContains(resp, reverse("admin:index"))

    def test_login_page_renders_without_app_chrome(self):
        self.client.logout()
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'id="palette"')


class HighlightFilterTest(TestCase):
    def test_marks_matches_and_escapes_html(self):
        from quotes.templatetags.passages import highlight

        self.assertEqual(highlight("Simplify, <b>simplify</b>", "simpl"),
                         "<mark>Simpl</mark>ify, &lt;b&gt;<mark>simpl</mark>ify&lt;/b&gt;")
        self.assertEqual(highlight("Tom & Jerry", "&"), "Tom <mark>&amp;</mark> Jerry")
        self.assertEqual(highlight("<i>x</i>", ""), "&lt;i&gt;x&lt;/i&gt;")
