from smtplib import SMTPException

from celery import current_app as app

from quotes.mail import find_quotes_and_send_email, users_due_for_email

import logging

logger = logging.getLogger(__name__)


@app.task(name="quotes.tasks.create_email_tasks")
def create_email_tasks():
    """Fan out a send task for each user whose local send time has arrived."""
    due = users_due_for_email()
    logger.info("Creating email tasks", extra={"due": len(due)})
    for user in due:
        send_email_task.delay(user.id)


@app.task(
    name="quotes.tasks.send_email_task",
    autoretry_for=(SMTPException,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_email_task(user_id: int, preview: bool = False):
    """Send today's passages to one user."""
    find_quotes_and_send_email(user_id, preview=preview)
