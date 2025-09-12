from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Quote, Book, User
from django.db import transaction, DataError
from django.urls import reverse_lazy
from .forms import QuoteCreateForm
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
import logging
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