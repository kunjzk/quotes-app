from quotes.models import Quote, Book, User
from django.db import transaction, DataError, IntegrityError, DatabaseError
from django.core.exceptions import ValidationError

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