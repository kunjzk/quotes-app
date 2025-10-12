from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from quotes.models import Book, Quote
from unittest.mock import patch
from django.db import DatabaseError

User = get_user_model()


class QuoteCreateViewTest(TestCase):
    """
    For the quote create view, we test the following:
    1. Test idempotent create view - double-posting same quote creates exactly one row
    2. Test that create view properly handles duplicate submissions
    """
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='poster',
            email='poster@example.com',
            password='pw'
        )
        self.book = Book.objects.create(
            title="Pragmatic Programmer", 
            author="Hunt/Thomas"
        )
    
    def test_create_view_happy_path(self):
        """
        Test that the create view properly handles a happy path.
        """
        assert self.client.login(username="poster", password="pw")
        payload = {
            "book": self.book.id,
            "quote": "Stone by stone.",
            "page_number": 100
        }
        resp = self.client.post(reverse("quotes:quote_create"), payload, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Stone by stone.", resp.content.decode())
    
    def test_idempotent_create_view(self):
        """
        Double-posting the same quote creates exactly one row and redirects cleanly.
        """
        # Login the user
        assert self.client.login(username="poster", password="pw")
        
        payload = {
            "book": self.book.id, 
            "quote": "Stone by stone.", 
            "page_number": ""
        }

        # First submit
        resp1 = self.client.post(reverse("quotes:quote_create"), payload, follow=False)
        self.assertIn(resp1.status_code, [302, 303])

        # Second (duplicate) submit
        resp2 = self.client.post(reverse("quotes:quote_create"), payload, follow=False)
        self.assertIn(resp2.status_code, [302, 303])

        # Exactly one row should exist
        quote_count = Quote.objects.filter(
            user=self.user, 
            book=self.book, 
            quote="Stone by stone."
        ).count()
        self.assertEqual(quote_count, 1)
    
    def test_create_view_with_incomplete_book_info(self):
        """
        Test that the create view properly handles incomplete book info.
        """
        assert self.client.login(username="poster", password="pw")
        payload = {
            "book": "",
            "quote": "Stone by stone.",
            "page_number": ""
        }
        resp = self.client.post(reverse("quotes:quote_create"), payload, follow=False)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Please select a book or enter both a title and author.", resp.content.decode())
    
    def test_create_view_with_book_selected_and_new_book_info(self):
        """
        Test that the create view properly handles both book info.
        """
        assert self.client.login(username="poster", password="pw")
        payload = {
            "book": self.book.id,
            "title": "Pragmatic Programmer",
            "author": "Hunt/Thomas",
            "quote": "Stone by stone.",
            "page_number": 100
        }
        resp = self.client.post(reverse("quotes:quote_create"), payload, follow=False)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("You can only EITHER: 1) select a book OR 2) enter both a title and author.", resp.content.decode())
    
    def test_create_view_atomicity_book_creation_fails(self):
        """
        Test that the create view handles validation errors gracefully and doesn't create anything.
        """
        assert self.client.login(username="poster", password="pw")
        
        # Count initial state
        initial_book_count = Book.objects.count()
        initial_quote_count = Quote.objects.count()
        
        payload = {
            "title": "a"*256,  # Too long - will cause validation error
            "author": "Hunt/Thomas",
            "quote": "Stone by stone.",
            "page_number": 100
        }
        resp = self.client.post(reverse("quotes:quote_create"), payload, follow=False)
        
        # Should return form with errors, not crash
        self.assertEqual(resp.status_code, 200)  # Form redisplayed with errors
        
        # Verify atomicity - nothing should be created
        self.assertEqual(Book.objects.count(), initial_book_count)
        self.assertEqual(Quote.objects.count(), initial_quote_count)
        
        # Verify error message is shown
        self.assertContains(resp, "Title must be less than 255 characters")

class QuoteListViewTest(TestCase):
    """
    For the quote list view, we test the following:
    1. Test list view scopes to current user - only shows current user's quotes
    2. Test that other users' quotes are not visible
    """
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create two users
        self.user1 = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='pw'
        )
        self.user2 = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='pw'
        )
        
        # Create a book
        self.book = Book.objects.create(
            title="Grokking Algorithms", 
            author="Bhargava"
        )
    
    def test_list_view_scopes_to_current_user(self):
        """
        Hitting 'quotes:quotes_list' only shows the current user's non-deleted quotes.
        """
        # Create quotes for both users
        q1 = Quote.objects.create(
            user=self.user1, 
            book=self.book, 
            quote="Greedy stays greedy."
        )
        Quote.objects.create(
            user=self.user2, 
            book=self.book, 
            quote="Graphs are friends."
        )

        # Login as alice
        assert self.client.login(username="alice", password="pw")
        resp = self.client.get(reverse("quotes:quotes_list"))
        self.assertEqual(resp.status_code, 200)

        # List should only include alice's quote
        quotes_in_context = list(resp.context["quotes"])
        self.assertEqual(len(quotes_in_context), 1)
        self.assertEqual(quotes_in_context[0].id, q1.id)
        self.assertEqual(quotes_in_context[0].quote, "Greedy stays greedy.")
