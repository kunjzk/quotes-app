from quotes.models import User
from celery import current_app as app
from quotes.services import find_quotes_and_send_email

@app.task
def create_email_tasks():
    """
    Create email tasks for each user in the DB.
    Fan out the tasks to send emails to each user.
    """
    print("Creating email tasks")
    for user in User.objects.all():
        send_email_task.delay(user)

@app.task
def send_email_task(user: User):
    """
    Send an email to the user.
    """
    print(f"Sending email to {user.email}")
    find_quotes_and_send_email(user.id)