"""Import quotes from Readwise CSV export.

Usage:
    python manage.py import_readwise <csv_file> <username>
    
Example:
    python manage.py import_readwise readwise-data.csv kunal
"""

import csv
import re
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from quotes.models import Book, Quote

User = get_user_model()


class Command(BaseCommand):
    help = 'Import quotes from Readwise CSV export'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to Readwise CSV file')
        parser.add_argument('username', type=str, help='Username to assign quotes to')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        username = options['username']
        dry_run = options.get('dry_run', False)

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        self.stdout.write(f'Importing quotes for user: {user.username}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be saved'))

        # Parse CSV and import
        imported = 0
        skipped = 0
        errors = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        result = self._import_quote(row, user, dry_run)
                        if result == 'imported':
                            imported += 1
                        elif result == 'skipped':
                            skipped += 1
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(f'Error importing quote: {str(e)[:100]}')
                        )

        except FileNotFoundError:
            raise CommandError(f'File not found: {csv_file}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {str(e)}')

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'✓ Imported: {imported}'))
        self.stdout.write(self.style.WARNING(f'⊘ Skipped (duplicates): {skipped}'))
        if errors > 0:
            self.stdout.write(self.style.ERROR(f'✗ Errors: {errors}'))
        self.stdout.write('='*60)

    def _import_quote(self, row, user, dry_run=False):
        """Import a single quote from CSV row."""
        
        # Extract data
        quote_text = row.get('Highlight', '').strip()
        full_title = row.get('Book Title', '').strip()
        author_str = row.get('Book Author', '').strip()
        
        if not quote_text or not full_title:
            return 'skipped'
        
        # Clean book title
        # Format: "Author - Title_With_Underscores-Publisher (Year)"
        # We want just the title part
        book_title = self._clean_book_title(full_title)
        
        # Clean author name
        # Format: "Last, First" -> "First Last"
        author = self._clean_author_name(author_str)
        
        if dry_run:
            self.stdout.write(
                f'Would import: "{quote_text[:60]}..." '
                f'from "{book_title}" by {author}'
            )
            return 'imported'
        
        # Get or create book
        with transaction.atomic():
            book, created = Book.objects.get_or_create(
                title=book_title,
                author=author,
                defaults={
                    'title': book_title,
                    'author': author
                }
            )
            
            # Check if quote already exists
            existing = Quote.objects.filter(
                quote=quote_text,
                book=book,
                user=user
            ).exists()
            
            if existing:
                return 'skipped'
            
            # Create quote
            Quote.objects.create(
                quote=quote_text,
                book=book,
                user=user,
                page_number=None  # Readwise doesn't include page numbers
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created book: {book_title} by {author}')
                )
        
        return 'imported'

    def _clean_book_title(self, full_title):
        """Extract clean book title from Readwise format.
        
        Input: "Greg McKeown - Essentialism_ The Disciplined Pursuit of Less-Crown Business (2014)"
        Output: "Essentialism: The Disciplined Pursuit of Less"
        """
        # Remove author prefix (everything before first " - ")
        if ' - ' in full_title:
            title = full_title.split(' - ', 1)[1]
        else:
            title = full_title
        
        # Remove publisher and year suffix (everything after last "-" before "(")
        # Pattern: "Title-Publisher (Year)" -> "Title"
        if '(' in title:
            title = re.sub(r'-[^-]+\([^)]+\)$', '', title)
        
        # Replace underscores with colons (Readwise uses _ for :)
        title = title.replace('_', ':')
        
        # Remove trailing hyphens
        title = title.rstrip('-').strip()
        
        return title

    def _clean_author_name(self, author_str):
        """Convert author name from 'Last, First' to 'First Last'.
        
        Input: "McKeown, Greg"
        Output: "Greg McKeown"
        """
        if not author_str:
            return ''
        
        # Handle "Last, First" format
        if ',' in author_str:
            parts = author_str.split(',', 1)
            if len(parts) == 2:
                last = parts[0].strip()
                first = parts[1].strip()
                return f'{first} {last}'
        
        return author_str.strip()
