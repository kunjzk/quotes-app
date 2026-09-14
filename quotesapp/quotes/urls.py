from django.urls import path

from . import views

app_name = "quotes"
urlpatterns = [
    # Marginalia main views
    path("", views.TodayView.as_view(), name="today"),
    path("today/", views.TodayView.as_view(), name="today"),
    path("shelf/", views.ShelfView.as_view(), name="shelf"),
    path("capture/", views.CaptureView.as_view(), name="capture"),
    path("photo/", views.ImageUploadView.as_view(), name="image_upload"),
    path("import/", views.BulkImportView.as_view(), name="bulk_import"),
    
    # HTMX endpoints
    path("api/book/<int:pk>/quotes/", views.BookQuotesView.as_view(), name="book_quotes"),
    path("api/book/suggest/", views.BookSuggestView.as_view(), name="book_suggest"),
    
    # Legacy views (keep for admin/compatibility)
    path("list/", views.QuotesListView.as_view(), name="quotes_list"),
    path("quote/<int:pk>/", views.QuoteDetailView.as_view(), name="quote_detail"),
    path("create/", views.QuoteCreateViewCustomForm.as_view(), name="quote_create"),
    path("quote/<int:pk>/edit/", views.QuoteUpdateView.as_view(), name="quote_edit"),
    path("quote/<int:pk>/delete/", views.QuoteSoftDeleteView.as_view(), name="quote_delete"),
]