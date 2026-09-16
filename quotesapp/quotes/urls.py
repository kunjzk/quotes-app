from django.urls import path

from . import views

app_name = "quotes"
urlpatterns = [
    # Marginalia main views
    path("", views.TodayView.as_view(), name="today"),
    path("today/", views.TodayView.as_view(), name="today"),
    path("today/preferences/", views.TodayPreferenceView.as_view(), name="today_preferences"),
    path("shelf/", views.ShelfView.as_view(), name="shelf"),
    path("capture/", views.CaptureView.as_view(), name="capture"),
    path("photo/", views.ImageUploadView.as_view(), name="image_upload"),
    path("import/", views.BulkImportView.as_view(), name="bulk_import"),
    
    # HTMX endpoints
    path("api/source/<int:pk>/quotes/", views.SourceQuotesView.as_view(), name="source_quotes"),
    path("api/source/suggest/", views.SourceSuggestView.as_view(), name="source_suggest"),
    path("api/creator/suggest/", views.CreatorSuggestView.as_view(), name="creator_suggest"),
    path("api/today/suggest/", views.TodaySuggestView.as_view(), name="today_suggest"),
    path("api/search/", views.SearchView.as_view(), name="search"),
    
    # Legacy views (keep for admin/compatibility)
    path("list/", views.QuotesListView.as_view(), name="quotes_list"),
    path("quote/<int:pk>/", views.QuoteDetailView.as_view(), name="quote_detail"),
    path("create/", views.QuoteCreateViewCustomForm.as_view(), name="quote_create"),
    path("quote/<int:pk>/edit/", views.QuoteUpdateView.as_view(), name="quote_edit"),
    path("quote/<int:pk>/delete/", views.QuoteSoftDeleteView.as_view(), name="quote_delete"),
]