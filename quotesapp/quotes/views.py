from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from .models import Quote, Source, User, TodayPreference
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
import math
import re
import csv
import io
from .services import (
    create_quote,
    filter_quotes_for_today,
    parse_attribution,
    get_today_preference,
    get_todays_quotes,
    search_passages,
    sources_on_shelf,
    suggest_today_values,
    update_today_preference,
)
from .ocr_service import OCRService
from .source_kinds import get_kind, kinds_context

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
        
        source = form.cleaned_data['source']
        title = form.cleaned_data['title']
        creator = form.cleaned_data['creator']
        quote = form.cleaned_data['quote']
        page_number = form.cleaned_data['page_number']

        result = create_quote(quote, source, title, creator, page_number, self.request.user)
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
        
        source = form.cleaned_data['source']
        title = form.cleaned_data['title']
        creator = form.cleaned_data['creator']

        if not source:
            if not (title and creator):
                form.add_error(None, "Please select a book or enter both a title and author.")
                return self.form_invalid(form)
        else:
            if title or creator:
                form.add_error(None, "You can only EITHER: 1) select a book OR 2) enter both a title and author.")
                return self.form_invalid(form)
        
        if not source and title and creator:
            # Create a new source if none selected but title/creator provided
            source = Source.objects.create(title=title, creator=creator)
            form.instance.source = source

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
    from which creator/source, is driven by the user's TodayPreference.
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
        context['matching_quotes'] = filter_quotes_for_today(user, preference.creator, preference.source_title).count()
        context['preference'] = preference
        context['is_filtered'] = bool(preference.creator or preference.source_title)
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
                creator=request.POST.get('creator', ''),
                source_title=request.POST.get('source', ''),
            )
        except ValidationError as e:
            messages = [msg for msgs in e.message_dict.values() for msg in msgs]
            return JsonResponse({'error': ' '.join(messages)}, status=400)

        return JsonResponse({
            'success': True,
            'quote_count': preference.quote_count,
            'creator': preference.creator,
            'source': preference.source_title,
        })


class TodaySuggestView(LoginRequiredMixin, View):
    """Autocomplete for the creator / source blanks on the Today screen."""

    def get(self, request):
        field = request.GET.get('field', '')
        if field not in ('creator', 'source'):
            return JsonResponse({'error': 'field must be "creator" or "source"'}, status=400)

        suggestions = suggest_today_values(
            request.user,
            field=field,
            query=request.GET.get('q', ''),
            creator=request.GET.get('creator', ''),
            source_title=request.GET.get('source', ''),
        )
        return JsonResponse({'suggestions': suggestions})


class CaptureView(LoginRequiredMixin, TemplateView):
    """Minimalist quote capture with inline attribution parsing."""
    template_name = 'quotes/capture.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {'source_kinds': kinds_context()}
    
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
        
        kind = get_kind(request.POST.get('kind')).value
        attribution = parse_attribution(attribution_line, kind) if attribution_line else {}
        source_title = attribution.get('title') or None
        creator = attribution.get('creator') or None

        # Match an existing source of this kind by title; otherwise create one.
        # create_quote takes either an existing source or a new title +
        # creator, never both.
        try:
            source = (
                Source.objects.filter(title__iexact=source_title, kind=kind).first()
                if source_title else None
            )
            if source_title and not source and not creator:
                source = Source.objects.create(title=source_title, creator='', kind=kind)

            result = create_quote(
                quote_text,
                source,
                None if source else source_title,
                None if source else creator,
                attribution.get('page_number'),
                request.user,
                kind=kind,
                timestamp_seconds=attribution.get('timestamp_seconds'),
            )
        except Exception as e:
            logger.error(f"Error creating quote: {e}")
            return JsonResponse({'error': 'Could not save the passage. Try again.'}, status=500)

        if result.status == "form_error":
            return JsonResponse({'error': result.error_message}, status=400)

        return JsonResponse({
            'success': True,
            'quote_id': result.quote.id,
            'source_title': result.quote.source.title,
            'kind': result.quote.source.kind,
            'location': result.quote.location_label,
            'message': 'Quote saved' if result.status == "success" else 'Quote already exists',
        })


class ShelfView(LoginRequiredMixin, TemplateView):
    """Visual bookshelf showing every source as a colored spine."""
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
            context['matching_source_ids'] = sorted({q.source_id for q in results})

        if self.request.GET.get('partial') == 'results':
            return context

        sources = list(sources_on_shelf(user))
        max_count = max((s.quote_count for s in sources), default=1)
        context['sources'] = [
            {
                'source': source,
                'color': self.spine_colors[i % len(self.spine_colors)],
                # Square-root scale relative to the fullest source, so a few very
                # large ones don't flatten everyone else to the same height.
                'height': int(140 + 180 * (source.quote_count / max_count) ** 0.5),
            }
            for i, source in enumerate(sources)
        ]
        context['total_sources'] = len(sources)
        context['total_passages'] = sum(s.quote_count for s in sources)

        selected = None
        requested = self.request.GET.get('source', '')
        if requested.isdigit():
            selected = next((s for s in sources if s.id == int(requested)), None)
        if selected is None and sources:
            selected = sources[0]
        context['selected_source'] = selected
        if selected:
            context['selected_quotes'] = self._quotes_for(selected)

        return context

    def _quotes_for(self, source):
        return quotes_in_source(source, self.request.user)


def quotes_in_source(source, user):
    """A user's passages from one source, in reading order."""
    return Quote.objects.filter(source=source, user=user).order_by('page_number', 'timestamp_seconds', 'id')


class SourceQuotesView(LoginRequiredMixin, TemplateView):
    """Fragment: the passages panel for one source on the shelf."""
    template_name = 'quotes/partials/source_quotes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        source = get_object_or_404(Source, pk=self.kwargs.get('pk'))
        context['source'] = source
        context['quotes'] = quotes_in_source(source, self.request.user)
        return context


class SearchView(LoginRequiredMixin, View):
    """JSON search across the user's passages, sources and creators for the search palette."""

    passage_limit = 8
    source_limit = 5

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse({'passages': [], 'sources': []})

        passages = search_passages(request.user, query)[:self.passage_limit]
        sources = sources_on_shelf(request.user).filter(
            Q(title__icontains=query) | Q(creator__icontains=query)
        )[:self.source_limit]

        return JsonResponse({
            'passages': [
                {
                    'id': quote.id,
                    'text': quote.quote[:240],
                    'source': quote.source.title,
                    'source_id': quote.source_id,
                    'location': quote.location_label,
                }
                for quote in passages
            ],
            'sources': [
                {
                    'id': source.id, 'title': source.title, 'creator': source.creator,
                    'count': source.quote_count, 'marker': source.marker,
                }
                for source in sources
            ],
        })


class SourceSuggestView(LoginRequiredMixin, View):
    """API endpoint: suggest sources as user types."""
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 2:
            return JsonResponse({'suggestions': []})
        
        # Get sources that have quotes from this user
        sources = Source.objects.filter(
            quote__user=request.user,
            title__icontains=query
        ).distinct()[:5]
        
        suggestions = [
            {'title': source.title, 'creator': source.creator, 'kind': source.kind}
            for source in sources
        ]
        
        return JsonResponse({'suggestions': suggestions})


class CreatorSuggestView(LoginRequiredMixin, View):
    """API endpoint: suggest creators as user types."""
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 2:
            return JsonResponse({'suggestions': []})
        
        # Get unique creators from sources that have quotes from this user
        creators = Source.objects.filter(
            quote__user=request.user,
            creator__icontains=query
        ).values_list('creator', flat=True).distinct()[:5]
        
        suggestions = [{'creator': creator} for creator in creators if creator]
        
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
        
        # Clean the Readwise book title and author
        title = self._clean_book_title(full_title)
        creator = self._clean_author_name(author_str)
        
        # Get or create the source
        with transaction.atomic():
            source, _ = Source.objects.get_or_create(
                title=title,
                creator=creator,
                defaults={'title': title, 'creator': creator}
            )
            
            # Check if quote already exists
            if Quote.objects.filter(quote=quote_text, source=source, user=user).exists():
                return 'skipped'
            
            # Create quote
            Quote.objects.create(
                quote=quote_text,
                source=source,
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

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {'source_kinds': kinds_context()}
    
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
            crop = self._parse_crop(request.POST)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        try:
            result = OCRService.extract_text_from_image(image_file, crop=crop)
            
            if not result:
                return JsonResponse({
                    'error': 'No text could be found. Try a clearer photo, or crop to just the page.'
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
                'lines': OCRService.preprocess_extracted_text(result.lines),
                'confidence': round(result.confidence, 1),
                'low_confidence': low_confidence,
                'message': 'Text extracted successfully'
            })
            
        except Exception as e:
            logger.error(f"Image upload error: {e}", exc_info=True)
            return JsonResponse({'error': f'Failed to process image: {str(e)}'}, status=500)

    # A crop smaller than this (as a fraction of each side) is almost
    # certainly a mis-tap rather than a deliberate selection.
    MIN_CROP_FRACTION = 0.02

    @classmethod
    def _parse_crop(cls, data):
        """
        Read the optional crop box (crop_x, crop_y, crop_w, crop_h), each a
        fraction of the photo as shown in the browser. Returns None when absent.
        """
        names = ('crop_x', 'crop_y', 'crop_w', 'crop_h')
        raw = [data.get(name, '').strip() for name in names]
        if not any(raw):
            return None
        try:
            x, y, w, h = (float(value) for value in raw)
        except ValueError:
            raise ValueError('The crop area is invalid. Choose the photo again and reselect the area.')
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            raise ValueError('The crop area is invalid. Choose the photo again and reselect the area.')

        # Allow for rounding in the browser, then clamp into the photo.
        eps = 0.001
        if x < -eps or y < -eps or x + w > 1 + eps or y + h > 1 + eps:
            raise ValueError('The crop area goes outside the photo. Reselect the area.')
        if w < cls.MIN_CROP_FRACTION or h < cls.MIN_CROP_FRACTION:
            raise ValueError('The crop area is too small. Drag the corners to include the passage.')
        x, y = max(0.0, x), max(0.0, y)
        return (x, y, min(w, 1 - x), min(h, 1 - y))


# Leaving here as a reference for the basic form view
# class QuoteCreateViewBasic(CreateView):
#     model = Quotes
#     template_name = 'quotes/create_quote.html'
#     fields = ['quote', 'page_number', 'source']

#     def form_valid(self, form):
#         # source = form.cleaned_data['source']
#         page_number = form.cleaned_data['page_number']
#         quote = form.cleaned_data['quote']

#         print(f"source: none, page_number: {page_number}, quote: {quote}")
#         return HttpResponse("Quote created successfully")