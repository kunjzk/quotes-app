from quotes.models import Quote, Book, User
from django.db import transaction, DataError, IntegrityError, DatabaseError
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging

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
    

def validate_quote_creation_input(quote_text: str, book: Book|None, title: str|None, author: str|None, page_number: int|None) -> None:
    """
    Validate user input for creating a quote.
    If the book is not provided, then both the title and author must be provided.
    If the book is provided, then the title and author must not be provided.
    """
    if not book:
        if not (title and author):
            raise ValueError("Please select a book or enter both a title and author.")
        if len(title) > 255:
            raise ValueError("Title must be less than 255 characters.")
        if len(author) > 255:
            raise ValueError("Author must be less than 255 characters.")
    else:
        if title or author:
            raise ValueError("You can only EITHER: 1) select a book OR 2) enter both a title and author.")
    
    if not quote_text:
        raise ValueError("Quote text is required.")
    
    if page_number and page_number < 0:
        raise ValueError("Page number must be greater than or equal to 0.")

def create_quote(quote_text: str, book: Book|None, title: str|None, author: str|None, page_number: int|None, user: User) -> QuoteCreationResult:
    """
    Create a quote.
    If the quote validation fails, then the error message is returned.
    If the quote already exists, then the quote id of the existing quote is returned.
    If the quote does not exist, then the quote is created.
    """
    try:
        validate_quote_creation_input(quote_text, book, title, author, page_number)
    except ValueError as e:
        return QuoteCreationResult(None, "form_error", None, str(e))
    
    with transaction.atomic():
        if not book:
            book, _ = Book.objects.get_or_create(
                    title=title,
                    author=author,
                )
        existing_quote = Quote.objects.filter(
            quote=quote_text,
            book=book,
            user=user,
        ).first()
        if existing_quote:
            return QuoteCreationResult(existing_quote, "quote_exists", existing_quote.id, None)
        else:
            quote = Quote(
                quote=quote_text,
                book=book,
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
    quotes = Quote.objects.filter(user=user).filter(deleted_at__isnull=True).order_by('?')[:3]
    if not quotes:
        logger.info(f"No quotes found for user {user.email}, not sending email")
        return
    
    date = timezone.now().strftime("%Y-%m-%d")
    authors_str = ", ".join([quote.book.author for quote in quotes[:-1]]) + f" and {quotes[-1].book.author}"
    subject = f"{date}: Quotes from {authors_str}"
    message = ""
    message += f"Dear {user.first_name},\n\n"
    message += f"Here are three quotes from your collection. Hope you enjoy them!\n\n"
    for quote in quotes:
        message += f"{quote.quote}\n"
        message += f"{quote.book.title} - {quote.book.author}\n"
        message += f"{quote.page_number}\n"
    message += "\n\nSee you tomorrow!\n\nBest regards,\nThe Quotes App"
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])