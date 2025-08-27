from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Books, Quotes

User = get_user_model()

# Create your tests here.
class QuoteModelTest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.book = Books.objects.create(
            title='Test Book',
            author='Test Author'
        )
    
    def test_create_quote(self):
        """Test creating a quote and checking it exists"""
        quote_text = "This is a test quote from the book."
        
        # Create a quote
        quote = Quotes.objects.create(
            quote=quote_text,
            book=self.book,
            user=self.user,
            page_number=42
        )
        
        # Check that the quote exists
        self.assertTrue(Quotes.objects.filter(id=quote.id).exists())
        
        # Check the quote content
        saved_quote = Quotes.objects.get(id=quote.id)
        self.assertEqual(saved_quote.quote, quote_text)
        self.assertEqual(saved_quote.book, self.book)
        self.assertEqual(saved_quote.user, self.user)
        self.assertEqual(saved_quote.page_number, 42)
        
        # Check string representation
        self.assertEqual(str(saved_quote), quote_text)
    
    def test_create_book(self):
        """Test creating a book and checking it exists"""
        book = Books.objects.create(
            title='Another Test Book',
            author='Another Author'
        )
        
        # Check that the book exists
        self.assertTrue(Books.objects.filter(id=book.id).exists())
        
        # Check the book content
        saved_book = Books.objects.get(id=book.id)
        self.assertEqual(saved_book.title, 'Another Test Book')
        self.assertEqual(saved_book.author, 'Another Author')
        
        # Check string representation
        self.assertEqual(str(saved_book), 'Another Test Book by author: Another Author')