"""Create the accounts the app expects to exist, on every start.

Passwords are only set when an account is first created, so a password
changed later is never silently reverted by a redeploy.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

WEAK_PASSWORDS = {"admin", "password", "kunal", "changeme"}


def _account_from_env(prefix, username, password, email, first_name, last_name):
    """Read one account's settings, allowing each field to be overridden."""
    return {
        "username": os.getenv(f"{prefix}_USERNAME", username),
        "password": os.getenv(f"{prefix}_PASSWORD", password),
        "email": os.getenv(f"{prefix}_EMAIL", email),
        "first_name": os.getenv(f"{prefix}_FIRST_NAME", first_name),
        "last_name": os.getenv(f"{prefix}_LAST_NAME", last_name),
    }


class Command(BaseCommand):
    help = "Idempotently create the admin and personal user accounts."

    def handle(self, *args, **options):
        # email is unique and non-blank on the custom user model, so every
        # seeded account needs a distinct address.
        domain = os.getenv("APP_DOMAIN", "localhost")

        accounts = [
            (
                _account_from_env(
                    "DJANGO_ADMIN",
                    username="admin",
                    password="admin",
                    email=f"admin@{domain}",
                    first_name="Site",
                    last_name="Administrator",
                ),
                True,
            ),
            (
                _account_from_env(
                    "DJANGO_USER",
                    username="kunal",
                    password="kunal",
                    email="kunal.rox@gmail.com",
                    first_name="Kunal",
                    last_name="Katarya",
                ),
                False,
            ),
        ]

        for account, is_superuser in accounts:
            self._seed(account, is_superuser)

    def _seed(self, account, is_superuser):
        username = account["username"]
        password = account["password"]

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": account["email"],
                    "first_name": account["first_name"],
                    "last_name": account["last_name"],
                    "is_staff": is_superuser,
                    "is_superuser": is_superuser,
                },
            )

            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(self.style.SUCCESS(f"created {username}"))
            else:
                # Keep privileges in sync without touching the password, so an
                # account cannot silently lose admin access on redeploy.
                if user.is_superuser != is_superuser or user.is_staff != is_superuser:
                    user.is_staff = is_superuser
                    user.is_superuser = is_superuser
                    user.save(update_fields=["is_staff", "is_superuser"])
                self.stdout.write(f"{username} already exists, left unchanged")

        if password in WEAK_PASSWORDS:
            self.stderr.write(
                self.style.WARNING(
                    f"{username} uses a weak default password. Override it with "
                    f"{'DJANGO_ADMIN' if is_superuser else 'DJANGO_USER'}_PASSWORD."
                )
            )
