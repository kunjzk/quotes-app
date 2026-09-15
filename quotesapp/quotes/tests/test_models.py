from django.test import TestCase
from django.contrib.auth import get_user_model
from quotes.models import Source, Quote, format_timestamp
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
    4. Changing the source and asserting the changes are saved
    5. Changing the user and asserting the changes are saved
    6. Changing the page number and asserting the changes are saved
    7. Soft deleting the quote and asserting it is excluded by the default manager, but included by the all_objects manager
    8. Test unique constraint on the quote field is enforced when the quote is not deleted
    9. Test unique constraint on the quote field is not enforced when the quote is deleted
    10. Test that a (hard) deleted quote no longer exists
    11. Test that two different users can create the same quote for the same source
    """
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.source = Source.objects.create(
            title='Test Book',
            creator='Test Author'
        )
        self.quote_text = "This is a test quote from the book."
        self.page_number = 42
    
    def test_create_quote(self):
        """Test creating a quote and checking it exists"""
        
        # Create a quote
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number
        )
        
        # Check that the quote exists
        self.assertTrue(Quote.objects.filter(id=quote.id).exists())
        
        # Check the quote content
        saved_quote = Quote.objects.get(id=quote.id)
        self.assertEqual(saved_quote.quote, self.quote_text)
        self.assertEqual(saved_quote.source, self.source)
        self.assertEqual(saved_quote.user, self.user)
        self.assertEqual(saved_quote.page_number, self.page_number)
    
    def test_str_representation(self):
        """Test the string representation of the quote"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        self.assertEqual(str(quote), self.quote_text)
    
    def test_change_quote(self):
        """Test changing the quote and asserting the changes are saved"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        quote.quote = "This is a changed quote from the book."
        quote.save()
        self.assertEqual(quote.quote, "This is a changed quote from the book.")
    
    def test_change_source(self):
        """Test changing the source and asserting the changes are saved"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        
        new_source = Source.objects.create(
            title='Another Test Book',
            creator='Another Author'
        )
        quote.source = new_source
        quote.save()
        self.assertEqual(quote.source, new_source)
    
    def test_change_user(self):
        """Test changing the user and asserting the changes are saved"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
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
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        quote.page_number = 43
        quote.save()
        self.assertEqual(quote.page_number, 43)
    
    def test_soft_delete_quote(self):
        """Test soft deleting the quote and asserting it is excluded by the default manager, but included by the all_objects manager"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        quote.deleted_at = timezone.now()
        quote.save()
        self.assertFalse(Quote.objects.filter(id=quote.id).exists())
        self.assertTrue(Quote.all_objects.filter(id=quote.id).exists())
    
    def test_unique_constraint_when_not_deleted(self):
        """Test unique constraint on the quote field is enforced when the quote is not deleted"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Quote.objects.create(
                    quote=self.quote_text,
                    source=self.source,
                    user=self.user,
                    page_number=self.page_number,
                )
    
    def test_unique_constraint_when_deleted(self):
        """Test unique constraint on the quote field is not enforced when a quote is soft deleted"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        quote.deleted_at = timezone.now()
        quote.save()
        
        quote_new = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number,
        )

        self.assertTrue(quote_new.quote == quote.quote)

    def test_hard_delete_quote(self):
        """Test that a hard deleted quote no longer exists"""
        quote = Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        self.assertTrue(Quote.objects.filter(id=quote.id).exists())
        quote.delete()
        self.assertFalse(Quote.objects.filter(id=quote.id).exists())

    def test_unique_constraint_when_different_users(self):
        """Test unique constraint on the quote field is enforced when the quote is not deleted and the users are different"""
        Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=self.user,
            page_number=self.page_number)
        new_user = User.objects.create(
            username='Another Test User',
            email='another@example.com',
            password='testpass123'
        )
        Quote.objects.create(
            quote=self.quote_text,
            source=self.source,
            user=new_user,
            page_number=self.page_number,
        )

class SourceModelTest(TestCase):
    """
    For the source model, we test the following:
    1. Creating a source, asserting it exists and asserting the content is correct
    2. Checking the string representation of the source
    3. Hard deleting the source and asserting it no longer exists
    4. Test that two identical sources cannot be created
    """
    def setUp(self):
        """Set up test data"""
        self.source = Source.objects.create(
            title='Test Book',
            creator='Test Author'
        )
    
    def test_create_source(self):
        """Test creating a source and checking it exists"""     
        # Check that the source exists
        self.assertTrue(Source.objects.filter(id=self.source.id).exists())
        
        # Check the source content
        saved_source = Source.objects.get(id=self.source.id)
        self.assertEqual(saved_source.title, 'Test Book')
        self.assertEqual(saved_source.creator, 'Test Author')

    def test_str_representation(self):
        """Test the string representation of the source"""
        self.assertEqual(str(self.source), 'Test Book by Test Author')
    
    def test_hard_delete_source(self):
        """Test that a hard deleted source no longer exists"""
        self.assertTrue(Source.objects.filter(id=self.source.id).exists())
        self.source.delete()
        self.assertFalse(Source.objects.filter(id=self.source.id).exists())
    
    def test_unique_constraint_when_identical(self):
        """Test that two identical sources cannot be created"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Source.objects.create(
                    title='Test Book',
                    creator='Test Author'
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


class QuoteLocationTest(TestCase):
    """A passage's position is a page for print and a timestamp for audio."""

    def setUp(self):
        self.user = User.objects.create_user(username='listener', email='listener@example.com', password='pw')
        self.source = Source.objects.create(title='Heroes', creator='David Bowie')

    def quote(self, **kwargs):
        return Quote.objects.create(user=self.user, source=self.source, quote='We can be heroes', **kwargs)

    def test_page(self):
        quote = self.quote(page_number=42)
        self.assertEqual((quote.location, quote.location_label), ('42', 'p. 42'))

    def test_timestamp(self):
        quote = self.quote(timestamp_seconds=151)
        self.assertEqual((quote.location, quote.location_label), ('2:31', '2:31'))

    def test_page_zero_still_counts(self):
        self.assertEqual(self.quote(page_number=0).location_label, 'p. 0')

    def test_page_wins_when_both_are_set(self):
        self.assertEqual(self.quote(page_number=7, timestamp_seconds=90).location_label, 'p. 7')

    def test_neither(self):
        quote = self.quote()
        self.assertEqual((quote.location, quote.location_label), ('', ''))

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), '0:00')
        self.assertEqual(format_timestamp(59), '0:59')
        self.assertEqual(format_timestamp(3599), '59:59')
        self.assertEqual(format_timestamp(3723), '1:02:03')

    def test_negative_timestamps_are_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.quote(timestamp_seconds=-1)
