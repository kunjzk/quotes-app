from django.http import HttpResponse
from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .models import Quotes, Books
from django import forms
from django.db import transaction
from django.urls import reverse_lazy

# Create your views here.
class QuotesListView(ListView):
    model = Quotes
    template_name = 'quotes/quotes_list.html'
    context_object_name = 'quotes'

class QuoteDetailView(DetailView):
    model = Quotes
    template_name = 'quotes/quote_detail.html'
    context_object_name = 'quote'

class QuoteCreateForm(forms.ModelForm):
    book = forms.ModelChoiceField(queryset=Books.objects.all(), required=False)
    title = forms.CharField(required=False)
    author = forms.CharField(required=False)

    class Meta:
        model = Quotes
        fields = ['quote', 'book', 'page_number']

class QuoteCreateViewBasic(CreateView):
    model = Quotes
    template_name = 'quotes/quote_debug.html'
    fields = ['quote', 'page_number', 'book']

    def form_valid(self, form):
        # book = form.cleaned_data['book']
        page_number = form.cleaned_data['page_number']
        quote = form.cleaned_data['quote']

        print(f"book: none, page_number: {page_number}, quote: {quote}")
        return HttpResponse("Quote created successfully")
    
class QuoteCreateViewCustomForm(CreateView):
    model = Quotes
    template_name = 'quotes/quote_debug.html'
    form_class = QuoteCreateForm
    success_url = reverse_lazy('quotes:quotes_list')  # Redirect to quote list
    
    @transaction.atomic
    def form_valid(self, form):
        book = form.cleaned_data['book']
        title = form.cleaned_data['title']
        author = form.cleaned_data['author']
        quote = form.cleaned_data['quote']
        page_number = form.cleaned_data['page_number']

        if not book:
            book = Books.objects.create(title=title, author=author)
            form.instance.book = book
        
        # Add this - create/get a default user
        from django.contrib.auth import get_user_model
        User = get_user_model()
        default_user, created = User.objects.get_or_create(
            username='default_user',
            defaults={'email': 'default@example.com'}
        )
        form.instance.user = default_user

        print(f"book: {book}, title: {title}, author: {author}, page_number: {page_number}, quote: {quote}")
        return super().form_valid(form)

class QuoteUpdateView(UpdateView):
    model = Quotes
    template_name = 'quotes/quote_edit.html'
    form_class = QuoteCreateForm
    success_url = reverse_lazy('quotes:quotes_list')
    
    def get_initial(self):
        """Pre-populate form with current book's title and author"""
        initial = super().get_initial()
        if self.object.book:
            initial['title'] = self.object.book.title
            initial['author'] = self.object.book.author
        return initial
    
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


