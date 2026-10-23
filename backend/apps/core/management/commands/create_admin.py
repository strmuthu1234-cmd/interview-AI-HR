"""Create an organisation and its first administrator (production bootstrap).

    python manage.py create_admin --org "Acme Corp" --username jane --email jane@acme.com
The password is read from $ADMIN_PASSWORD or prompted – never passed on the command line.
"""
import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.accounts.models import Organization, User


class Command(BaseCommand):
    help = "Create an organisation (if needed) and an administrator user."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)

    def handle(self, *args, **o):
        if User.objects.filter(username=o["username"]).exists():
            raise CommandError("That username already exists.")
        pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password: ")
        try:
            validate_password(pw)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        org, _ = Organization.objects.get_or_create(slug=slugify(o["org"]), defaults={"name": o["org"]})
        User.objects.create_user(username=o["username"], email=o["email"], password=pw, role=User.Role.ADMIN, organization=org)
        self.stdout.write(self.style.SUCCESS(f"Administrator '{o['username']}' created for organisation '{org.name}'."))
