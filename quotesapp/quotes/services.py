from quotes.models import Quote, Book, User

class QuoteCreationResult:
    def __init__(self, quote: Quote, book: Book, user: User):
        self.quote = quote
        self.book = book
        self.user = user