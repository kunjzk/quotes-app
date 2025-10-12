from celery import shared_task

@shared_task
def send_email():
    print("Sending email")