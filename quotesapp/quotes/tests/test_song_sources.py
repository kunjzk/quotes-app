from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from quotes.models import Quote, Source
from quotes.ocr_service import build_ocr_result
from quotes.services import (
    create_quote,
    filter_quotes_for_today,
    parse_attribution,
    search_passages,
    suggest_today_values,
)
from quotes.source_kinds import SOURCE_KINDS, get_kind, kinds_context
from quotes.tests.test_ocr import tesseract_data

User = get_user_model()

LYRIC = "We can be heroes\nJust for one day"


class SourceKindsTest(SimpleTestCase):
    def test_unknown_and_blank_values_fall_back_to_book(self):
        for value in ("", None, "podcast", "  "):
            self.assertEqual(get_kind(value).value, "book")

    def test_values_are_matched_case_insensitively(self):
        self.assertEqual(get_kind("SONG").value, "song")

    def test_definitions_reach_the_pages_complete(self):
        kinds = kinds_context()
        self.assertEqual([k["value"] for k in kinds], list(SOURCE_KINDS))
        for kind in kinds:
            self.assertEqual(
                set(kind),
                {"value", "label", "title_label", "creator_label", "collection_label",
                 "attribution_hint", "locator", "locator_label", "locator_hint",
                 "marker", "keeps_line_breaks"},
            )

    def test_songs_keep_line_breaks_and_books_do_not(self):
        self.assertTrue(get_kind("song").keeps_line_breaks)
        self.assertFalse(get_kind("book").keeps_line_breaks)


class SourceModelKindTest(TestCase):
    def test_defaults_to_book(self):
        self.assertEqual(Source.objects.create(title="Walden", creator="Thoreau").kind, "book")

    def test_same_title_and_creator_can_be_a_book_and_a_song(self):
        # Born to Run is both a Springsteen memoir and a Springsteen song.
        Source.objects.create(title="Born to Run", creator="Bruce Springsteen", kind="book")
        song = Source.objects.create(title="Born to Run", creator="Bruce Springsteen", kind="song")
        self.assertEqual(Source.objects.filter(title="Born to Run").count(), 2)
        self.assertEqual(song.marker, "♪")

    def test_duplicates_within_a_kind_are_still_rejected(self):
        Source.objects.create(title="Heroes", creator="David Bowie", kind="song")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Source.objects.create(title="Heroes", creator="David Bowie", kind="song")


class ParseAttributionTest(SimpleTestCase):
    def test_book_page(self):
        self.assertEqual(
            parse_attribution("— walden | Henry David Thoreau | p. 90"),
            {"title": "walden", "creator": "Henry David Thoreau", "collection": "",
             "page_number": 90, "timestamp_seconds": None},
        )

    def test_song_album(self):
        parsed = parse_attribution("— Lazarus | David Bowie | Blackstar | 2:31", kind="song")
        self.assertEqual(parsed, {
            "title": "Lazarus", "creator": "David Bowie", "collection": "Blackstar",
            "page_number": None, "timestamp_seconds": 151,
        })

    def test_books_have_no_collection(self):
        parsed = parse_attribution("— Walden | Thoreau | Modern Library | p. 90")
        self.assertEqual(parsed["collection"], "")

    def test_song_timestamp(self):
        parsed = parse_attribution("— Heroes | David Bowie | 2:31", kind="song")
        self.assertEqual(parsed, {"title": "Heroes", "creator": "David Bowie", "collection": "",
                                  "page_number": None, "timestamp_seconds": 151})

    def test_song_timestamp_variants(self):
        for text, seconds in [("Heroes at 2:31", 151), ("Heroes 0:07", 7), ("A Day in the Life 1:02:03", 3723)]:
            self.assertEqual(parse_attribution(text, kind="song")["timestamp_seconds"], seconds)

    def test_a_song_title_with_numbers_is_not_read_as_a_position(self):
        parsed = parse_attribution("— 99 Problems | Jay-Z", kind="song")
        self.assertEqual((parsed["title"], parsed["timestamp_seconds"]), ("99 Problems", None))

    def test_page_markers_are_only_read_for_books(self):
        self.assertIsNone(parse_attribution("Heroes p. 90", kind="song")["timestamp_seconds"])
        self.assertEqual(parse_attribution("Heroes p. 90", kind="song")["title"], "Heroes p. 90")

    def test_timestamps_are_only_read_for_songs(self):
        parsed = parse_attribution("Slaughterhouse 5 | Vonnegut", kind="book")
        self.assertEqual((parsed["title"], parsed["page_number"]), ("Slaughterhouse 5", None))

    def test_title_only(self):
        self.assertEqual(parse_attribution("— Notebook")["title"], "Notebook")


class CreateSongQuoteTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="listener", email="l@example.com", password="pw")

    def test_creates_the_source_with_its_kind_and_timestamp(self):
        result = create_quote(LYRIC, None, "Heroes", "David Bowie", None, self.user, kind="song", timestamp_seconds=151)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.quote.source.kind, "song")
        self.assertEqual(result.quote.timestamp_seconds, 151)
        self.assertEqual(result.quote.location_label, "2:31")

    def test_a_song_and_a_book_of_the_same_name_stay_apart(self):
        book = create_quote("Prose", None, "Born to Run", "Bruce Springsteen", 12, self.user).quote.source
        song = create_quote("Lyric", None, "Born to Run", "Bruce Springsteen", None, self.user, kind="song").quote.source
        self.assertNotEqual(book.pk, song.pk)


class CaptureSongTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="listener", email="l@example.com", password="pw")
        self.client.login(username="listener", password="pw")

    def post(self, content, **extra):
        return self.client.post(reverse("quotes:capture"), {"content": content, **extra})

    def test_saves_a_lyric_with_its_line_breaks_and_timestamp(self):
        data = self.post(f"{LYRIC}\n— Heroes | David Bowie | 2:31", kind="song").json()
        quote = Quote.objects.get(pk=data["quote_id"])
        self.assertEqual(quote.quote, LYRIC)
        self.assertEqual((quote.source.kind, quote.source.creator, quote.timestamp_seconds), ("song", "David Bowie", 151))
        self.assertEqual((data["kind"], data["location"]), ("song", "2:31"))

    def test_matches_an_existing_song_rather_than_a_book_of_the_same_name(self):
        book = Source.objects.create(title="Born to Run", creator="Bruce Springsteen", kind="book")
        song = Source.objects.create(title="Born to Run", creator="Bruce Springsteen", kind="song")
        data = self.post("Tramps like us\n— Born to Run", kind="song").json()
        self.assertEqual(Quote.objects.get(pk=data["quote_id"]).source, song)
        self.assertFalse(Quote.objects.filter(source=book).exists())

    def test_without_a_kind_it_is_still_a_book(self):
        data = self.post("A line.\n— Notebook").json()
        self.assertEqual(Quote.objects.get(pk=data["quote_id"]).source.kind, "book")

    def test_an_unknown_kind_falls_back_to_book(self):
        data = self.post("A line.\n— Notebook", kind="hologram").json()
        self.assertEqual(Quote.objects.get(pk=data["quote_id"]).source.kind, "book")

    def test_suggestions_carry_the_kind(self):
        song = Source.objects.create(title="Heroes", creator="David Bowie", kind="song")
        Quote.objects.create(user=self.user, source=song, quote=LYRIC)
        data = self.client.get(reverse("quotes:source_suggest"), {"q": "her"}).json()
        self.assertEqual(
            data["suggestions"],
            [{"title": "Heroes", "creator": "David Bowie", "kind": "song", "collection": ""}],
        )

    def test_the_capture_page_carries_the_kind_definitions(self):
        resp = self.client.get(reverse("quotes:capture"))
        self.assertContains(resp, 'id="source-kinds"')
        self.assertContains(resp, 'data-kind="song"')


class SongDisplayTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="listener", email="l@example.com", password="pw")
        self.client.login(username="listener", password="pw")
        self.song = Source.objects.create(title="Heroes", creator="David Bowie", kind="song")
        self.lyric = Quote.objects.create(user=self.user, source=self.song, quote=LYRIC)

    def test_today_margin_falls_back_to_the_kind_marker(self):
        self.assertEqual(self.lyric.margin_label, "♪")
        resp = self.client.get(reverse("quotes:today"))
        self.assertContains(resp, '<div class="folio">♪</div>', html=False)

    def test_a_timestamp_wins_over_the_marker(self):
        self.lyric.timestamp_seconds = 151
        self.assertEqual(self.lyric.margin_label, "2:31")

    def test_multi_line_lyrics_are_set_smaller(self):
        self.assertFalse(self.lyric.is_long)
        self.lyric.quote = "one\ntwo\nthree\nfour"
        self.assertTrue(self.lyric.is_long)

    def test_the_shelf_marks_songs(self):
        resp = self.client.get(reverse("quotes:shelf"))
        self.assertContains(resp, '<span class="k" aria-hidden="true">♪</span>', html=False)
        self.assertContains(resp, "Song · 1 passage")


class OCRLinesTest(SimpleTestCase):
    """Lyrics keep their lines; the reflowed version is still there for prose."""

    def test_both_layouts_are_returned(self):
        lines = [
            (1, 1, 1, 100, 100, "We can be heroes"),
            (1, 1, 2, 100, 155, "Just for one day"),
            (1, 1, 3, 100, 245, "We can be us"),
        ]
        result = build_ocr_result(tesseract_data(lines))
        self.assertEqual(result.text, "We can be heroes Just for one day\n\nWe can be us")
        self.assertEqual(result.lines, "We can be heroes\nJust for one day\n\nWe can be us")

    def test_empty_read(self):
        result = build_ocr_result(tesseract_data([]))
        self.assertEqual((result.text, result.lines), ("", ""))


class AlbumTest(TestCase):
    """A song's album: another way to fill the source blank on Today."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="listener", email="l@example.com", password="pw")
        self.client.login(username="listener", password="pw")
        self.lazarus = Source.objects.create(
            title="Lazarus", creator="David Bowie", kind="song", collection="Blackstar"
        )
        self.dollar = Source.objects.create(
            title="Dollar Days", creator="David Bowie", kind="song", collection="Blackstar"
        )
        self.walden = Source.objects.create(title="Walden", creator="Henry David Thoreau")
        Quote.objects.create(user=self.user, source=self.lazarus, quote="Look up here, I'm in heaven")
        Quote.objects.create(user=self.user, source=self.dollar, quote="I'm dying to push their backs against the grain")
        Quote.objects.create(user=self.user, source=self.walden, quote="Simplify, simplify.", page_number=91)

    def test_the_source_blank_takes_an_album(self):
        quotes = filter_quotes_for_today(self.user, source_title="Blackstar")
        self.assertEqual({q.source for q in quotes}, {self.lazarus, self.dollar})

    def test_a_song_title_still_wins_over_a_partial_album_match(self):
        quotes = filter_quotes_for_today(self.user, source_title="Lazarus")
        self.assertEqual([q.source for q in quotes], [self.lazarus])

    def test_suggestions_offer_songs_and_albums(self):
        self.assertEqual(
            suggest_today_values(self.user, "source", creator="David Bowie"),
            ["Blackstar", "Dollar Days", "Lazarus"],
        )
        self.assertEqual(suggest_today_values(self.user, "source", query="black"), ["Blackstar"])

    def test_books_never_offer_a_collection(self):
        self.assertEqual(suggest_today_values(self.user, "source", creator="Henry David Thoreau"), ["Walden"])

    def test_search_matches_albums(self):
        found = search_passages(self.user, "blackstar")
        self.assertEqual({q.source for q in found}, {self.lazarus, self.dollar})

    def test_capture_records_the_album(self):
        data = self.client.post(reverse("quotes:capture"), {
            "content": "Something happened on the day he died\n— Blackstar | David Bowie | Blackstar | 4:12",
            "kind": "song",
        }).json()
        source = Quote.objects.get(pk=data["quote_id"]).source
        self.assertEqual((source.title, source.collection, source.kind), ("Blackstar", "Blackstar", "song"))

    def test_an_album_given_later_fills_in_the_song_saved_without_one(self):
        song = Source.objects.create(title="Heroes", creator="David Bowie", kind="song")
        self.client.post(reverse("quotes:capture"), {
            "content": "We can be heroes\n— Heroes | David Bowie | Heroes | 2:31",
            "kind": "song",
        })
        song.refresh_from_db()
        self.assertEqual(song.collection, "Heroes")
        self.assertEqual(Source.objects.filter(title="Heroes", kind="song").count(), 1)

    def test_an_album_is_not_overwritten(self):
        self.client.post(reverse("quotes:capture"), {
            "content": "Look up here\n— Lazarus | David Bowie | Greatest Hits | 0:10",
            "kind": "song",
        })
        self.lazarus.refresh_from_db()
        self.assertEqual(self.lazarus.collection, "Blackstar")

    def test_books_ignore_a_third_part(self):
        self.client.post(reverse("quotes:capture"), {
            "content": "A line.\n— Walden | Henry David Thoreau | Modern Library | p. 5",
        })
        self.walden.refresh_from_db()
        self.assertEqual(self.walden.collection, "")


class CriteriaSentenceTest(TestCase):
    def test_the_sentence_reads_by_author_from_source(self):
        user = User.objects.create_user(username="reader", email="r@example.com", password="pw")
        source = Source.objects.create(title="Walden", creator="Henry David Thoreau")
        Quote.objects.create(user=user, source=source, quote="Simplify, simplify.")
        self.client.login(username="reader", password="pw")
        content = self.client.get(reverse("quotes:today")).content.decode()
        self.assertIn("I want to see", content)
        self.assertIn("author from", content)
        self.assertIn("source.", content)
        self.assertNotIn("author in", content)
