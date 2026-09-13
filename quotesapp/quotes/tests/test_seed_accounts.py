from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

User = get_user_model()


class SeedAccountsTest(TestCase):
    """
    For the seed_accounts command, we test the following:
    1. The admin account is created as a superuser
    2. The personal account is created without staff or superuser rights
    3. Both accounts can log in with their seeded passwords
    4. Running the command twice creates no duplicates
    5. A password changed after seeding survives a re-run
    6. Credentials can be overridden by environment variables
    7. A pre-existing account that lost admin rights has them restored
    """

    def test_creates_admin_as_superuser(self):
        call_command("seed_accounts")

        admin = User.objects.get(username="admin")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)

    def test_creates_personal_account_without_privileges(self):
        call_command("seed_accounts")

        kunal = User.objects.get(username="kunal")
        self.assertFalse(kunal.is_superuser)
        self.assertFalse(kunal.is_staff)

    def test_seeded_passwords_work(self):
        call_command("seed_accounts")

        self.assertTrue(User.objects.get(username="admin").check_password("admin"))
        self.assertTrue(User.objects.get(username="kunal").check_password("kunal"))

    def test_is_idempotent(self):
        call_command("seed_accounts")
        call_command("seed_accounts")

        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        self.assertEqual(User.objects.filter(username="kunal").count(), 1)

    def test_does_not_reset_a_changed_password(self):
        call_command("seed_accounts")

        admin = User.objects.get(username="admin")
        admin.set_password("something-stronger")
        admin.save()

        call_command("seed_accounts")

        admin.refresh_from_db()
        self.assertTrue(admin.check_password("something-stronger"))
        self.assertFalse(admin.check_password("admin"))

    def test_environment_overrides_credentials(self):
        env = {
            "DJANGO_ADMIN_USERNAME": "root",
            "DJANGO_ADMIN_PASSWORD": "s3cret-pw",
        }
        with mock.patch.dict("os.environ", env):
            call_command("seed_accounts")

        self.assertFalse(User.objects.filter(username="admin").exists())
        root = User.objects.get(username="root")
        self.assertTrue(root.is_superuser)
        self.assertTrue(root.check_password("s3cret-pw"))

    def test_restores_lost_admin_rights(self):
        call_command("seed_accounts")

        admin = User.objects.get(username="admin")
        admin.is_superuser = False
        admin.is_staff = False
        admin.save()

        call_command("seed_accounts")

        admin.refresh_from_db()
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
