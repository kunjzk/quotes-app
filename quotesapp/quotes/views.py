from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView
from .models import Quotes, Books
from django import forms

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
    class Meta:
        model = Quotes
        fields = ['quote', 'book', 'page_number']

class QuoteCreateView(CreateView):
    model = Quotes
    template_name = 'quotes/quote_create.html'
    context_object_name = 'books'
    form_class = QuoteCreateForm

    def form_valid(self, form):
        book_id = self.request.POST.get('book_id')
        title = self.request.POST.get('title')
        author = self.request.POST.get('author')
        page_number = self.request.POST.get('page_number')

        if book_id:
            book = Books.objects.get(id=book_id)
        else:
            book = Books.objects.create(title=title, author=author)
        
        quote_instance = form.save(commit=False)
        quote_instance.book = book
        quote_instance.save()
        return super().form_valid(form)
    
    


