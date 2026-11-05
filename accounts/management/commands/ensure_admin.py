"""Render free plan এ shell নেই — তাই deploy এর সময় env থেকে admin তৈরি/আপডেট হয়।
ADMIN_PHONE, ADMIN_PASSWORD (এবং ঐচ্ছিক ADMIN_NAME, ADMIN_EMAIL) সেট করুন।"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.utils import normalize_phone


class Command(BaseCommand):
    help = "Create/update the admin user from ADMIN_PHONE / ADMIN_PASSWORD env variables"

    def handle(self, *args, **options):
        phone = os.environ.get("ADMIN_PHONE")
        password = os.environ.get("ADMIN_PASSWORD")
        if not phone or not password:
            self.stdout.write("ADMIN_PHONE/ADMIN_PASSWORD সেট নেই — admin তৈরি করা হয়নি।")
            return
        User = get_user_model()
        phone = normalize_phone(phone)
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"name": os.environ.get("ADMIN_NAME", "Admin"), "email": os.environ.get("ADMIN_EMAIL") or None},
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin {'created' if created else 'updated'}: {phone}"))
