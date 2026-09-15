from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from .models import Quote, Book, User, TodayPreference
from django.db import transaction, DataError
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import QuoteCreateForm, UserRegistrationForm
from django.utils import timezone
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Count, Q
import logging
import re
import csv
import io
from .services import (
    books_on_shelf,
    create_quote,
    filter_quotes_for_today,
    get_today_preference,
    get_todays_quotes,
    search_passages,
    suggest_today_values,
    update_today_preference,
)
from .ocr_service import OCRService

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
        next_url = request.POST.get("next", "")
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect("quotes:quotes_list")


# Marginalia Views

class TodayView(LoginRequiredMixin, TemplateView):
    """
    Show today's quotes - the same quotes throughout the day. How many, and
    from which author/book, is driven by the user's TodayPreference.
    """
    template_name = 'quotes/today.html'
    pages_template_name = 'quotes/partials/today_pages.html'

    def get_template_names(self):
        # The criteria sentence refetches just the passages after a change.
        if self.request.GET.get('partial') == 'pages':
            return [self.pages_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        preference = get_today_preference(user)

        context['quotes'] = get_todays_quotes(user, preference)
        context['total_quotes'] = Quote.objects.filter(user=user).count()
        context['matching_quotes'] = filter_quotes_for_today(user, preference.author, preference.book_title).count()
        context['preference'] = preference
        context['is_filtered'] = bool(preference.author or preference.book_title)
        context['min_quote_count'] = TodayPreference.MIN_QUOTE_COUNT
        context['max_quote_count'] = TodayPreference.MAX_QUOTE_COUNT
        context['default_quote_count'] = TodayPreference.DEFAULT_QUOTE_COUNT

        return context


class TodayPreferenceView(LoginRequiredMixin, View):
    """Save the fill-in-the-blank criteria from the Today screen."""

    def post(self, request):
        raw_count = request.POST.get('quote_count', '').strip()
        try:
            quote_count = int(raw_count)
        except ValueError:
            return JsonResponse({'error': 'Number of quotes must be a whole number'}, status=400)

        try:
            preference = update_today_preference(
                request.user,
                quote_count=quote_count,
                author=request.POST.get('author', ''),
                book_title=request.POST.get('book', ''),
            )
        except ValidationError as e:
            messages = [msg for msgs in e.message_dict.values() for msg in msgs]
            return JsonResponse({'error': ' '.join(messages)}, status=400)

        return JsonResponse({
            'success': True,
            'quote_count': preference.quote_count,
            'author': preference.author,
            'book': preference.book_title,
        })


class TodaySuggestView(LoginRequiredMixin, View):
    """Autocomplete for the author / book blanks on the Today screen."""

    def get(self, request):
        field = request.GET.get('field', '')
        if field not in ('author', 'book'):
            return JsonResponse({'error': 'field must be "author" or "book"'}, status=400)

        suggestions = suggest_today_values(
            request.user,
            field=field,
            query=request.GET.get('q', ''),
            author=request.GET.get('author', ''),
            book_title=request.GET.get('book', ''),
        )
        return JsonResponse({'suggestions': suggestions})


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
            page_match = re.search(r'\b(?:p\.?|page)\s*(\d+)', attr, re.IGNORECASE)
            if page_match:
                page_number = int(page_match.group(1))
                # Remove page number from attribution
                attr = re.sub(r'\s*\b(?:p\.?|page)\s*\d+', '', attr, flags=re.IGNORECASE).strip()
            
            # Check for author pattern: "book | author"
            if '|' in attr:
                parts = attr.split('|')
                book_title = parts[0].strip()
                author = parts[1].strip() if len(parts) > 1 else None
            else:
                book_title = attr
        
        # Match an existing book by title; otherwise create one. create_quote
        # takes either an existing book or a new title + author, never both.
        try:
            book = Book.objects.filter(title__iexact=book_title).first() if book_title else None
            if book_title and not book and not author:
                book = Book.objects.create(title=book_title, author='')

            result = create_quote(
                quote_text,
                book,
                None if book else book_title,
                None if book else author,
                page_number,
                request.user,
            )
        except Exception as e:
            logger.error(f"Error creating quote: {e}")
            return JsonResponse({'error': 'Could not save the passage. Try again.'}, status=500)

        if result.status == "form_error":
            return JsonResponse({'error': result.error_message}, status=400)

        return JsonResponse({
            'success': True,
            'quote_id': result.quote.id,
            'book_title': result.quote.book.title,
            'message': 'Quote saved' if result.status == "success" else 'Quote already exists',
        })


class ShelfView(LoginRequiredMixin, TemplateView):
    """Visual bookshelf showing all books as colored spines."""
    template_name = 'quotes/shelf.html'
    results_template_name = 'quotes/partials/passage_results.html'
    spine_colors = ['spine-color-1', 'spine-color-2', 'spine-color-3',
                    'spine-color-4', 'spine-color-5', 'spine-color-6']

    def get_template_names(self):
        # The shelf filter refetches just the results panel as you type.
        if self.request.GET.get('partial') == 'results':
            return [self.results_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        query = self.request.GET.get('q', '').strip()

        if query:
            results = list(search_passages(user, query))
            context['query'] = query
            context['results'] = results
            context['matching_book_ids'] = sorted({q.book_id for q in results})

        if self.request.GET.get('partial') == 'results':
            return context

        books = list(books_on_shelf(user))
        max_count = max((b.quote_count for b in books), default=1)
        context['books'] = [
            {
                'book': book,
                'color': self.spine_colors[i % len(self.spine_colors)],
                # Square-root scale relative to the fullest book, so a few very
                # large books don't flatten everyone else to the same height.
                'height': int(140 + 180 * (book.quote_count / max_count) ** 0.5),
            }
            for i, book in enumerate(books)
        ]
        context['total_books'] = len(books)
        context['total_passages'] = sum(b.quote_count for b in books)

        selected = None
        requested = self.request.GET.get('book', '')
        if requested.isdigit():
            selected = next((b for b in books if b.id == int(requested)), None)
        if selected is None and books:
            selected = books[0]
        context['selected_book'] = selected
        if selected:
            context['selected_quotes'] = self._quotes_for(selected)

        return context

    def _quotes_for(self, book):
        return Quote.objects.filter(book=book, user=self.request.user).order_by('page_number', 'id')


class BookQuotesView(LoginRequiredMixin, TemplateView):
    """Fragment: the passages panel for one book on the shelf."""
    template_name = 'quotes/partials/book_quotes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = get_object_or_404(Book, pk=self.kwargs.get('pk'))
        context['book'] = book
        context['quotes'] = Quote.objects.filter(book=book, user=self.request.user).order_by('page_number', 'id')
        return context


class SearchView(LoginRequiredMixin, View):
    """JSON search across the user's passages, books and authors for the search palette."""

    passage_limit = 8
    book_limit = 5

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse({'passages': [], 'books': []})

        passages = search_passages(request.user, query)[:self.passage_limit]
        books = books_on_shelf(request.user).filter(
            Q(title__icontains=query) | Q(author__icontains=query)
        )[:self.book_limit]

        return JsonResponse({
            'passages': [
                {
                    'id': quote.id,
                    'text': quote.quote[:240],
                    'book': quote.book.title,
                    'book_id': quote.book_id,
                    'page': quote.page_number,
                }
                for quote in passages
            ],
            'books': [
                {'id': book.id, 'title': book.title, 'author': book.author, 'count': book.quote_count}
                for book in books
            ],
        })


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


class AuthorSuggestView(LoginRequiredMixin, View):
    """API endpoint: suggest authors as user types."""
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 2:
            return JsonResponse({'suggestions': []})
        
        # Get unique authors from books that have quotes from this user
        authors = Book.objects.filter(
            quote__user=request.user,
            author__icontains=query
        ).values_list('author', flat=True).distinct()[:5]
        
        suggestions = [{'author': author} for author in authors if author]
        
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


class RegisterView(CreateView):
    """User registration view."""
    template_name = 'registration/register.html'
    form_class = UserRegistrationForm
    success_url = reverse_lazy('quotes:today')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        # Log the user in after registration. The user didn't come from
        # authenticate(), so name the backend explicitly; login() requires it
        # once more than one backend is configured.
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        return response


class ImageUploadView(LoginRequiredMixin, TemplateView):
    """Upload image and extract text using OCR."""
    template_name = 'quotes/image_upload.html'
    
    def post(self, request):
        if 'image' not in request.FILES:
            return JsonResponse({'error': 'No image uploaded'}, status=400)
        
        image_file = request.FILES['image']
        
        if image_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'Image too large (max 10MB)'}, status=400)
        
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({
                'error': f'Invalid file type. Allowed types: JPEG, PNG, WebP'
            }, status=400)
        
        try:
            result = OCRService.extract_text_from_image(image_file)
            
            if not result:
                return JsonResponse({
                    'error': 'No text could be extracted from the image. Please try a clearer image.'
                }, status=400)
            
            cleaned_text = OCRService.preprocess_extracted_text(result.text)
            low_confidence = result.confidence < OCRService.LOW_CONFIDENCE_THRESHOLD
            
            logger.info(
                "Image OCR completed",
                extra={
                    "user_id": request.user.id,
                    "text_length": len(cleaned_text),
                    "confidence": round(result.confidence, 1),
                    "rotation": result.rotation,
                }
            )
            
            return JsonResponse({
                'success': True,
                'text': cleaned_text,
                'confidence': round(result.confidence, 1),
                'low_confidence': low_confidence,
                'message': 'Text extracted successfully'
            })
            
        except Exception as e:
            logger.error(f"Image upload error: {e}", exc_info=True)
            return JsonResponse({'error': f'Failed to process image: {str(e)}'}, status=500)


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