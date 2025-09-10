from django.test import TestCase
from django.contrib.auth import get_user_model
from quotes.models import Books, Quotes
from django.utils import timezone
from django.db import IntegrityError, transaction

User = get_user_model()

# Create your tests here.
class QuoteModelTest(TestCase):
    """
    For the quotes model, we test the following:
    1. Creating a quote and asserting it exists
    2. Checking the string representation of the quote
    3. Changing the quote and asserting the changes are saved
    4. Changing the book and asserting the changes are saved
    5. Changing the user and asserting the changes are saved
    6. Changing the page number and asserting the changes are saved
    7. Soft deleting the quote and asserting it is excluded by the default manager, but included by the all_objects manager
    8. Test unique constraint on the quote field is enforced when the quote is not deleted
    9. Test unique constraint on the quote field is not enforced when the quote is deleted
    10. Test that a (hard) deleted quote no longer exists
    11. Test that two different users can create the same quote for the same book
    """
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
        self.quote_text = "This is a test quote from the book."
        self.page_number = 42
    
    def test_create_quote(self):
        """Test creating a quote and checking it exists"""
        
        # Create a quote
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number
        )
        
        # Check that the quote exists
        self.assertTrue(Quotes.objects.filter(id=quote.id).exists())
        
        # Check the quote content
        saved_quote = Quotes.objects.get(id=quote.id)
        self.assertEqual(saved_quote.quote, self.quote_text)
        self.assertEqual(saved_quote.book, self.book)
        self.assertEqual(saved_quote.user, self.user)
        self.assertEqual(saved_quote.page_number, self.page_number)
    
    def test_str_representation(self):
        """Test the string representation of the quote"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        self.assertEqual(str(quote), self.quote_text)
    
    def test_change_quote(self):
        """Test changing the quote and asserting the changes are saved"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        quote.quote = "This is a changed quote from the book."
        quote.save()
        self.assertEqual(quote.quote, "This is a changed quote from the book.")
    
    def test_change_book(self):
        """Test changing the book and asserting the changes are saved"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        
        new_book = Books.objects.create(
            title='Another Test Book',
            author='Another Author'
        )
        quote.book = new_book
        quote.save()
        self.assertEqual(quote.book, new_book)
    
    def test_change_user(self):
        """Test changing the user and asserting the changes are saved"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        new_user = User.objects.create(
            username='Another Test User',
            email='another@example.com',
            password='testpass123'
        )
        quote.user = new_user
        quote.save()
        self.assertEqual(quote.user, new_user)
    
    def test_change_page_number(self):
        """Test changing the page number and asserting the changes are saved"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        quote.page_number = 43
        quote.save()
        self.assertEqual(quote.page_number, 43)
    
    def test_soft_delete_quote(self):
        """Test soft deleting the quote and asserting it is excluded by the default manager, but included by the all_objects manager"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        quote.deleted_at = timezone.now()
        quote.save()
        self.assertFalse(Quotes.objects.filter(id=quote.id).exists())
        self.assertTrue(Quotes.all_objects.filter(id=quote.id).exists())
    
    def test_unique_constraint_when_not_deleted(self):
        """Test unique constraint on the quote field is enforced when the quote is not deleted"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Quotes.objects.create(
                    quote=self.quote_text,
                    book=self.book,
                    user=self.user,
                    page_number=self.page_number,
                )
    
    def test_unique_constraint_when_deleted(self):
        """Test unique constraint on the quote field is not enforced when a quote is soft deleted"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        quote.deleted_at = timezone.now()
        quote.save()
        
        quote_new = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number,
        )

        self.assertTrue(quote_new.quote == quote.quote)

    def test_hard_delete_quote(self):
        """Test that a hard deleted quote no longer exists"""
        quote = Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        self.assertTrue(Quotes.objects.filter(id=quote.id).exists())
        quote.delete()
        self.assertFalse(Quotes.objects.filter(id=quote.id).exists())

    def test_unique_constraint_when_different_users(self):
        """Test unique constraint on the quote field is enforced when the quote is not deleted and the users are different"""
        Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=self.user,
            page_number=self.page_number)
        new_user = User.objects.create(
            username='Another Test User',
            email='another@example.com',
            password='testpass123'
        )
        Quotes.objects.create(
            quote=self.quote_text,
            book=self.book,
            user=new_user,
            page_number=self.page_number,
        )

class BookModelTest(TestCase):
    """
    For the books model, we test the following:
    1. Creating a book, asserting it exists and asserting the content is correct
    2. Checking the string representation of the book
    3. Hard deleting the book and asserting it no longer exists
    4. Test that two identical books cannot be created
    """
    def setUp(self):
        """Set up test data"""
        self.book = Books.objects.create(
            title='Test Book',
            author='Test Author'
        )
    
    def test_create_book(self):
        """Test creating a book and checking it exists"""     
        # Check that the book exists
        self.assertTrue(Books.objects.filter(id=self.book.id).exists())
        
        # Check the book content
        saved_book = Books.objects.get(id=self.book.id)
        self.assertEqual(saved_book.title, 'Test Book')
        self.assertEqual(saved_book.author, 'Test Author')

    def test_str_representation(self):
        """Test the string representation of the book"""
        self.assertEqual(str(self.book), 'Test Book by Test Author')
    
    def test_hard_delete_book(self):
        """Test that a hard deleted book no longer exists"""
        self.assertTrue(Books.objects.filter(id=self.book.id).exists())
        self.book.delete()
        self.assertFalse(Books.objects.filter(id=self.book.id).exists())
    
    def test_unique_constraint_when_identical(self):
        """Test that two identical books cannot be created"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Books.objects.create(
                    title='Test Book',
                    author='Test Author'
                )

class UserModelTest(TestCase):
    """
    For the user model, we test the following:
    1. Creating a user, asserting they exist
    2. Checking the string representation of the user
    3. Changing the user and asserting the changes are saved
    4. Hard deleting the user and asserting it no longer exists
    """
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
    
    def test_create_user(self):
        """Test creating a user and asserting they exist"""
        self.assertTrue(User.objects.filter(id=self.user.id).exists())
    
    def test_str_representation(self):
        """Test the string representation of the user"""
        result = str(self.user)
        self.assertEqual(result, 'testuser - test@example.com')
    
    def test_change_user(self):
        """Test changing the user and asserting the changes are saved"""
        self.user.username = 'Another Test User'
        self.user.save()
        self.assertEqual(self.user.username, 'Another Test User')
    
    def test_hard_delete_user(self):
        """Test that a hard deleted user no longer exists"""
        self.assertTrue(User.objects.filter(id=self.user.id).exists())
        self.user.delete()
        self.assertFalse(User.objects.filter(id=self.user.id).exists())