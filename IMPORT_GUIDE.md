# Importing Readwise Quotes - Deployment Guide

## Overview
This guide explains how to import your Readwise quotes into the production database.

## What's Been Created
A Django management command (`import_readwise`) that:
- Parses Readwise CSV exports
- Cleans book titles (removes publisher info and formatting)
- Converts author names from "Last, First" to "First Last"
- Creates books and quotes in the database
- Handles duplicates automatically
- Assigns all quotes to a specified user

## Deployment Steps

### Option 1: Run via Django Management Command (Recommended)

1. **Upload the CSV file to the server**
   ```bash
   scp -i ~/.ssh/deploy.pem readwise-data.csv ubuntu@<server-ip>:/tmp/
   ```

2. **SSH into the server**
   ```bash
   ssh -i ~/.ssh/deploy.pem ubuntu@<server-ip>
   ```

3. **Navigate to the app directory**
   ```bash
   cd /opt/quotesapp
   ```

4. **Run the import command (dry-run first to test)**
   ```bash
   sudo docker compose -f docker-compose.prod.yml run --rm quotes-app \
     python manage.py import_readwise /tmp/readwise-data.csv kunal --dry-run
   ```

5. **If dry-run looks good, run the actual import**
   ```bash
   sudo docker compose -f docker-compose.prod.yml run --rm quotes-app \
     python manage.py import_readwise /tmp/readwise-data.csv kunal
   ```

6. **Clean up**
   ```bash
   rm /tmp/readwise-data.csv
   ```

### Option 2: Via Deployment Workflow (Easier)

Since you'll need to deploy the new code anyway (for the import command), you can:

1. **Trigger deployment workflow** (as discussed earlier)
   - Go to: https://github.com/kunjzk/quotes-app/actions/workflows/deploy-aws.yml
   - Click "Run workflow"
   - Type "deploy" in confirmation
   - Run workflow

2. **Once deployed, follow steps 1-6 from Option 1** to upload and import the CSV

## What Happens During Import

The command will:
1. Read each row from the CSV
2. Extract the quote text, book title, and author
3. Clean the book title (e.g., "Greg McKeown - Essentialism_ The Disciplined Pursuit of Less-Crown Business (2014)" → "Essentialism: The Disciplined Pursuit of Less")
4. Convert author format (e.g., "McKeown, Greg" → "Greg McKeown")
5. Create or find the book in the database
6. Create the quote (skip if duplicate)
7. Assign to the specified user

## Expected Results

From your CSV (296 quotes):
- **Books**: ~10-15 unique books will be created
- **Quotes**: 296 quotes will be imported
- **Duplicates**: Any existing quotes will be skipped
- **Page Numbers**: None (Readwise doesn't export page numbers)

## Verification

After import, check:
```bash
# View quote count
sudo docker compose -f docker-compose.prod.yml run --rm quotes-app \
  python manage.py shell -c "from quotes.models import Quote; print(f'Total quotes: {Quote.objects.count()}')"

# View book count  
sudo docker compose -f docker-compose.prod.yml run --rm quotes-app \
  python manage.py shell -c "from quotes.models import Book; print(f'Total books: {Book.objects.count()}')"
```

Or simply login to the Marginalia UI and check:
- **Today**: Should show 3 random quotes
- **Shelf**: Should show all your books with colored spines
- **Capture**: Ready for new quotes

## Notes

- The import is idempotent - you can run it multiple times safely
- Duplicates are detected by matching quote text + book + user
- No page numbers will be set (Readwise CSV doesn't include them)
- All quotes are assigned to the user you specify (`kunal`)

## Troubleshooting

If import fails:
1. Check CSV file format matches Readwise export
2. Ensure user exists: `python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print(User.objects.filter(username='kunal').exists())"`
3. Check Docker container logs: `sudo docker compose -f docker-compose.prod.yml logs quotes-app`
