from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from .models import Quote, Book, User
from django.db import transaction, DataError
from django.urls import reverse_lazy
from .forms import QuoteCreateForm
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Count, Q
import logging
import random
import re
import csv
import io
from .services import create_quote

logger = logging.getLogger(__name__)

# Create your views here.

class UserQuotesQuerySetMixin:
    """Mixin to filter quotes to only show the current user's quotes"""
    def get_queryset(self):
        return Quote.objects.filter(user=self.request.user)

class QuotesListView(LoginRequiredMixin, UserQuotesQuerySetMixin, ListView):
    model = Quote
    template_name = 'quotes/list_quotes.html'
    context_object_name = 'quotes'

class QuoteDetailView(LoginRequiredMixin, UserQuotesQuerySetMixin, DetailView):
    model = Quote
    template_name = 'quotes/view_quote.html'
    context_object_name = 'quote'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        logger.info(
            "Quote viewed",
            extra={
                "user_id": self.request.user.id,
                "quote_id": obj.pk,
            }
        )
        return obj
  
class QuoteCreateViewCustomForm(LoginRequiredMixin, CreateView):
    model = Quote
    template_name = 'quotes/create_quote.html'
    form_class = QuoteCreateForm
    context_object_name = 'quote'
    success_url = reverse_lazy('quotes:quotes_list')  # Redirect to quote list
    
    def form_valid(self, form):      
        # Automatically assign the logged-in user
        form.instance.user = self.request.user
        
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']
        quote = form.cleaned_data['quote']
        page_number = form.cleaned_data['page_number']

        result = create_quote(quote, book, title, author, page_number, self.request.user)
        if result.status == "form_error":
            form.add_error(None, result.error_message)
            return self.form_invalid(form)
        elif result.status == "quote_exists":
            return redirect('quotes:quote_detail', pk=result.existing_quote_id)
        else: 
            # result.status == "success"
            return redirect(self.success_url)
        
class QuoteUpdateView(LoginRequiredMixin, UserQuotesQuerySetMixin, UpdateView):
    model = Quote
    template_name = 'quotes/update_quote.html'
    form_class = QuoteCreateForm
    success_url = reverse_lazy('quotes:quotes_list')
    context_object_name = 'quote'
    
    @transaction.atomic
    def form_valid(self, form):
        # Keep the original user (don't allow changing user on update)
        # form.instance.user is already set from the existing quote
        
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']

        if not book:
            if not (title and author):
                form.add_error(None, "Please select a book or enter both a title and author.")
                return self.form_invalid(form)
        else:
            if title or author:
                form.add_error(None, "You can only EITHER: 1) select a book OR 2) enter both a title and author.")
                return self.form_invalid(form)
        
        if not book and title and author:
            # Create new book if none selected but title/author provided
            book = Book.objects.create(title=title, author=author)
            form.instance.book = book

        logger.info(
            "Quote updated",
            extra={
                "user_id": self.request.user.id,
                "quote_id": form.instance.pk,
            }
        )
        
        return super().form_valid(form)

class QuoteSoftDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Filter to only user's quotes for security
        quote = get_object_or_404(Quote.all_objects, pk=pk, user=self.request.user)
        quote.deleted_at = timezone.now()
        quote.save(update_fields=["deleted_at"])
        logger.info(
            "Quote soft deleted",
            extra={
                "user_id": self.request.user.id,
                "quote_id": quote.pk,
            }
        )
        return redirect("quotes:quotes_list")


# Marginalia Views

class TodayView(LoginRequiredMixin, TemplateView):
    """Show today's 3 quotes - the same quotes throughout the day."""
    template_name = 'quotes/today.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get user's quotes
        user_quotes = Quote.objects.filter(user=self.request.user)
        
        # Select 3 random quotes (same seed per day for consistency)
        today_seed = timezone.now().date().toordinal()
        random.seed(today_seed + self.request.user.id)
        
        all_quotes = list(user_quotes)
        if len(all_quotes) >= 3:
            todays_quotes = random.sample(all_quotes, 3)
        else:
            todays_quotes = all_quotes
        
        # Calculate reading streak (days with quotes)
        # Simple version: count total quotes / 3 (assuming 3 quotes per day)
        streak = max(1, len(all_quotes) // 3)
        
        context['quotes'] = todays_quotes
        context['streak'] = streak
        context['total_quotes'] = len(all_quotes)
        
        return context


class CaptureView(LoginRequiredMixin, TemplateView):
    """Minimalist quote capture with inline attribution parsing."""
    template_name = 'quotes/capture.html'
    
    def post(self, request):
        content = request.POST.get('content', '').strip()
        
        if not content:
            return JsonResponse({'error': 'Quote cannot be empty'}, status=400)
        
        # Parse the content: quote, then attribution line like "— walden p. 90"
        # Pattern: everything before the last line starting with em dash or hyphen
        lines = content.split('\n')
        
        attribution_line = None
        quote_lines = lines
        
        # Check if last line is attribution (starts with — or -)
        if lines and (lines[-1].strip().startswith('—') or lines[-1].strip().startswith('-')):
            attribution_line = lines[-1].strip()
            quote_lines = lines[:-1]
        
        quote_text = '\n'.join(quote_lines).strip()
        
        if not quote_text:
            return JsonResponse({'error': 'Quote text cannot be empty'}, status=400)
        
        # Parse attribution: "— book p. 123" or "— book" or "— book | author"
        book_title = None
        author = None
        page_number = None
        
        if attribution_line:
            # Remove leading dashes
            attr = attribution_line.lstrip('—-').strip()
            
            # Check for page number pattern: "p. 123" or "p.123" or "page 123"
            page_match = re.search(r'(?:p\.?|page)\s*(\d+)', attr, re.IGNORECASE)
            if page_match:
                page_number = int(page_match.group(1))
                # Remove page number from attribution
                attr = re.sub(r'\s*(?:p\.?|page)\s*\d+', '', attr, flags=re.IGNORECASE).strip()
            
            # Check for author pattern: "book | author"
            if '|' in attr:
                parts = attr.split('|')
                book_title = parts[0].strip()
                author = parts[1].strip() if len(parts) > 1 else None
            else:
                book_title = attr
        
        # Try to find or create the book
        book = None
        if book_title:
            # Try exact match first
            book = Book.objects.filter(title__iexact=book_title).first()
            
            # If no book found and we have an author, create new book
            if not book and author:
                book = Book.objects.create(title=book_title, author=author)
            elif not book:
                # Just title, no author - create with empty author
                book = Book.objects.create(title=book_title, author='')
        
        # Create the quote
        try:
            result = create_quote(
                quote=quote_text,
                book=book,
                title=book_title or '',
                author=author or '',
                page_number=page_number,
                user=request.user
            )
            
            if result.status == "success" or result.status == "quote_exists":
                quote_id = result.existing_quote_id if result.status == "quote_exists" else Quote.objects.filter(user=request.user).latest('created_at').id
                return JsonResponse({
                    'success': True,
                    'quote_id': quote_id,
                    'message': 'Quote saved' if result.status == "success" else 'Quote already exists'
                })
            else:
                return JsonResponse({'error': result.error_message}, status=400)
                
        except Exception as e:
            logger.error(f"Error creating quote: {e}")
            return JsonResponse({'error': str(e)}, status=500)


class ShelfView(LoginRequiredMixin, TemplateView):
    """Visual bookshelf showing all books as colored spines."""
    template_name = 'quotes/shelf.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all books that have quotes from this user
        books = Book.objects.filter(
            quote__user=self.request.user
        ).annotate(
            quote_count=Count('quote', filter=Q(quote__user=self.request.user))
        ).filter(quote_count__gt=0).distinct().order_by('-quote_count', 'title')
        
        # Assign colors to books (cycle through 6 colors)
        colors = ['spine-color-1', 'spine-color-2', 'spine-color-3', 
                  'spine-color-4', 'spine-color-5', 'spine-color-6']
        
        books_with_colors = []
        for i, book in enumerate(books):
            books_with_colors.append({
                'book': book,
                'color': colors[i % len(colors)],
                'height': min(300, 80 + (book.quote_count * 20))  # Height based on quote count
            })
        
        context['books'] = books_with_colors
        context['total_books'] = len(books)
        context['total_passages'] = sum(b['book'].quote_count for b in books_with_colors)
        
        return context


class BookQuotesView(LoginRequiredMixin, TemplateView):
    """HTMX endpoint: return quotes for a specific book."""
    template_name = 'quotes/partials/book_quotes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_id = self.kwargs.get('pk')
        
        book = get_object_or_404(Book, pk=book_id)
        quotes = Quote.objects.filter(book=book, user=self.request.user).order_by('page_number')
        
        context['book'] = book
        context['quotes'] = quotes
        
        return context


class BookSuggestView(LoginRequiredMixin, View):
    """HTMX endpoint: suggest books as user types."""
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 2:
            return JsonResponse({'suggestions': []})
        
        # Get books that have quotes from this user
        books = Book.objects.filter(
            quote__user=request.user,
            title__icontains=query
        ).distinct()[:5]
        
        suggestions = [{'title': book.title, 'author': book.author} for book in books]
        
        return JsonResponse({'suggestions': suggestions})


class BulkImportView(LoginRequiredMixin, TemplateView):
    """Bulk import quotes from Readwise CSV."""
    template_name = 'quotes/bulk_import.html'
    
    def post(self, request):
        if 'csv_file' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
        
        csv_file = request.FILES['csv_file']
        
        # Validate file type
        if not csv_file.name.endswith('.csv'):
            return JsonResponse({'error': 'Please upload a CSV file'}, status=400)
        
        # Validate file size (max 10MB)
        if csv_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File too large (max 10MB)'}, status=400)
        
        try:
            # Read and parse CSV
            file_data = csv_file.read().decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(file_data))
            
            imported = 0
            skipped = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (accounting for header)
                try:
                    result = self._import_quote(row, request.user)
                    if result == 'imported':
                        imported += 1
                    elif result == 'skipped':
                        skipped += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)[:100]}")
                    if len(errors) >= 10:  # Limit error messages
                        errors.append("... and more errors")
                        break
            
            return JsonResponse({
                'success': True,
                'imported': imported,
                'skipped': skipped,
                'errors': errors
            })
            
        except Exception as e:
            logger.error(f"Bulk import error: {e}")
            return JsonResponse({'error': f'Import failed: {str(e)}'}, status=500)
    
    def _import_quote(self, row, user):
        """Import a single quote from CSV row."""
        quote_text = row.get('Highlight', '').strip()
        full_title = row.get('Book Title', '').strip()
        author_str = row.get('Book Author', '').strip()
        
        if not quote_text or not full_title:
            return 'skipped'
        
        # Clean book title and author
        book_title = self._clean_book_title(full_title)
        author = self._clean_author_name(author_str)
        
        # Get or create book
        with transaction.atomic():
            book, _ = Book.objects.get_or_create(
                title=book_title,
                author=author,
                defaults={'title': book_title, 'author': author}
            )
            
            # Check if quote already exists
            if Quote.objects.filter(quote=quote_text, book=book, user=user).exists():
                return 'skipped'
            
            # Create quote
            Quote.objects.create(
                quote=quote_text,
                book=book,
                user=user,
                page_number=None
            )
        
        return 'imported'
    
    def _clean_book_title(self, full_title):
        """Extract clean book title from Readwise format."""
        if ' - ' in full_title:
            title = full_title.split(' - ', 1)[1]
        else:
            title = full_title
        
        if '(' in title:
            title = re.sub(r'-[^-]+\([^)]+\)$', '', title)
        
        title = title.replace('_', ':').rstrip('-').strip()
        return title
    
    def _clean_author_name(self, author_str):
        """Convert 'Last, First' to 'First Last'."""
        if not author_str:
            return ''
        
        if ',' in author_str:
            parts = author_str.split(',', 1)
            if len(parts) == 2:
                return f'{parts[1].strip()} {parts[0].strip()}'
        
        return author_str.strip()


# Leaving here as a reference for the basic form view
# class QuoteCreateViewBasic(CreateView):
#     model = Quotes
#     template_name = 'quotes/create_quote.html'
#     fields = ['quote', 'page_number', 'book']

#     def form_valid(self, form):
#         # book = form.cleaned_data['book']
#         page_number = form.cleaned_data['page_number']
#         quote = form.cleaned_data['quote']

#         print(f"book: none, page_number: {page_number}, quote: {quote}")
#         return HttpResponse("Quote created successfully")