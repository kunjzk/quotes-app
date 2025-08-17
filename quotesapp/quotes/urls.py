from django.urls import path

from . import views

app_name = "quotes"
urlpatterns = [
    path("", views.QuotesListView.as_view(), name="quotes_list"),
    path("<int:pk>/", views.QuoteDetailView.as_view(), name="quote_detail"),
    path("create/", views.QuoteCreateView.as_view(), name="quote_create"),
]