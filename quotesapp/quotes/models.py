from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db.models import Q, UniqueConstraint

# Create your models here.

class QuoteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class Quote(models.Model):
    quote = models.TextField()
    book = models.ForeignKey('Book', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    page_number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = QuoteManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["quote", "user", "book"],
                condition=Q(deleted_at__isnull=True),
                name="unique_quote_per_user_per_book_when_not_deleted"
            )
        ]

    def __str__(self):
        return self.quote

class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["title", "author"],
                name="unique_title_author"
            )
        ]

    def __str__(self):
        return f"{self.title} by {self.author}"

class User(AbstractUser):
    email = models.EmailField(unique=True, blank=False)
    first_name = models.CharField(max_length=255, blank=False)
    last_name = models.CharField(max_length=255, blank=False)

    def __str__(self):
        return f"{self.username} - {self.email}"