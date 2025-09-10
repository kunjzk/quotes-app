from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Quotes, Books, User
from django.db import transaction
from django.urls import reverse_lazy
from .forms import QuoteCreateForm
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
import logging

logger = logging.getLogger(__name__)

# Create your views here.

class UserQuotesQuerySetMixin:
    """Mixin to filter quotes to only show the current user's quotes"""
    def get_queryset(self):
        return Quotes.objects.filter(user=self.request.user)

class QuotesListView(LoginRequiredMixin, UserQuotesQuerySetMixin, ListView):
    model = Quotes
    template_name = 'quotes/list_quotes.html'
    context_object_name = 'quotes'

class QuoteDetailView(LoginRequiredMixin, UserQuotesQuerySetMixin, DetailView):
    model = Quotes
    template_name = 'quotes/view_quote.html'
    context_object_name = 'quote'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        logger.info(
            "Quote viewed",
            extra={
                "user": self.request.user.username,
                "quote_id": obj.pk,
            }
        )
        return obj
  
class QuoteCreateViewCustomForm(LoginRequiredMixin, CreateView):
    model = Quotes
    template_name = 'quotes/create_quote.html'
    form_class = QuoteCreateForm
    context_object_name = 'quote'
    success_url = reverse_lazy('quotes:quotes_list')  # Redirect to quote list
    
    def form_valid(self, form):
        from django.db import IntegrityError
        
        # Automatically assign the logged-in user
        form.instance.user = self.request.user
        
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']
        quote = form.cleaned_data['quote']
        page_number = form.cleaned_data['page_number']

        # Handle book creation with get_or_create for idempotency
        if not book and title and author:
            book, _ = Books.objects.get_or_create(
                title=title, 
                author=author,
            )
            form.instance.book = book
        
        # Try to create the quote, handle duplicates gracefully
        try:
            with transaction.atomic():
                result = super().form_valid(form)
                logger.info(
                    "Quote created",
                    extra={
                        "user": self.request.user.username,
                        "quote_id": form.instance.pk,
                        "book": str(book) if book else None,
                        "title": title,
                        "author": author,
                        "page_number": page_number,
                    }
                )
                return result
        except IntegrityError:
            # Quote already exists - find it and redirect (idempotent behavior)
            existing_quote = Quotes.objects.get(
                quote=quote,
                user=self.request.user,
                book=book
            )
            logger.info(
                "Quote exists, redirecting to detail view",
                extra={
                    "user": self.request.user.username,
                    "existing_quote_id": existing_quote.pk,
                }
            )
            return redirect('quotes:quote_detail', pk=existing_quote.pk)

class QuoteUpdateView(LoginRequiredMixin, UserQuotesQuerySetMixin, UpdateView):
    model = Quotes
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
        
        if not book and title and author:
            # Create new book if none selected but title/author provided
            book = Books.objects.create(title=title, author=author)
            form.instance.book = book

        logger.info(
            "Quote updated",
            extra={
                "user": self.request.user.username,
                "quote_id": form.instance.pk,
            }
        )
        
        return super().form_valid(form)

class QuoteSoftDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        # Filter to only user's quotes for security
        quote = get_object_or_404(Quotes.all_objects, pk=pk, user=self.request.user)
        quote.deleted_at = timezone.now()
        quote.save(update_fields=["deleted_at"])
        logger.info(
            "Quote soft deleted",
            extra={
                "user": self.request.user.username,
                "quote_id": quote.pk,
            }
        )
        return redirect("quotes:quotes_list")


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