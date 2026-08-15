# Quotes App

## How to run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env file with your values (or use the defaults provided)
make up
```

Go to `localhost:8000` on browser to view app.

## Accessing Services

- **App**: http://localhost:8000
- **MailHog (Email Testing)**: http://localhost:8025
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## Email Testing

The app uses **MailHog** for local email testing. All emails sent by the application will be captured by MailHog and can be viewed in the web interface at http://localhost:8025.

### Testing Email Functionality

1. **Create test data:**
   - Go to http://localhost:8000
   - Create a user account
   - Add at least 3 quotes (with different books)

2. **Trigger email manually via Django shell:**
   ```bash
   docker-compose exec quotes-app python manage.py shell
   ```
   Then run:
   ```python
   from quotes.tasks import send_email_task
   send_email_task.delay(1)  # Replace 1 with your user ID
   exit()
   ```

3. **View the email:**
   - Open http://localhost:8025 in your browser
   - You should see the email with 3 random quotes from your collection

4. **Scheduled emails:**
   - The Celery beat scheduler automatically sends emails daily at 7:30 AM UTC
   - Check the `quotes-celery-beat` logs to verify the schedule: `docker-compose logs -f quotes-celery-beat`

## What make up does

1. Run postgres image locally with the values saved in .env
2. Run Redis for Celery task queue
3. Run MailHog for email testing
4. Build app image locally & run it once all services are ready
5. Creates a volume for postgres to persist data independently of container lifecycle
