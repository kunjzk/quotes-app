from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Quotes, Books, User
from django.db import transaction
from django.urls import reverse_lazy
from .forms import QuoteCreateForm
from django.utils import timezone

# Create your views here.
class QuotesListView(ListView):
    model = Quotes
    template_name = 'quotes/list_quotes.html'
    context_object_name = 'quotes'

class QuoteDetailView(DetailView):
    model = Quotes
    template_name = 'quotes/view_quote.html'
    context_object_name = 'quote'
  
class QuoteCreateViewCustomForm(CreateView):
    model = Quotes
    template_name = 'quotes/create_quote.html'
    form_class = QuoteCreateForm
    context_object_name = 'quote'
    success_url = reverse_lazy('quotes:quotes_list')  # Redirect to quote list
    
    @transaction.atomic
    def form_valid(self, form):
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']
        quote = form.cleaned_data['quote']
        page_number = form.cleaned_data['page_number']
        user = form.cleaned_data['user']
        
        if not book:
            book = Books.objects.create(title=title, author=author)
            form.instance.book = book
        
        print(f"book: {book}, title: {title}, author: {author}, page_number: {page_number}, quote: {quote}, user: {user}")
        return super().form_valid(form)

class QuoteUpdateView(UpdateView):
    model = Quotes
    template_name = 'quotes/update_quote.html'
    form_class = QuoteCreateForm
    success_url = reverse_lazy('quotes:quotes_list')
    context_object_name = 'quote'
    
    @transaction.atomic
    def form_valid(self, form):
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']
        
        if not book and title and author:
            # Create new book if none selected but title/author provided
            book = Books.objects.create(title=title, author=author)
            form.instance.book = book
        
        return super().form_valid(form)

class QuoteSoftDeleteView(View):
    def post(self, request, pk):
        quote = get_object_or_404(Quotes.all_objects, pk=pk)
        quote.deleted_at = timezone.now()
        quote.save(update_fields=["deleted_at"])
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