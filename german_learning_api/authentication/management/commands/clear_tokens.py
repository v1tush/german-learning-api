from django.core.management.base import BaseCommand
from django.utils import timezone

from authentication.models import RefreshToken


class Command(BaseCommand):
    help = "Delete all expired refresh tokens from database."

    def handle(self, *args, **options):
        tokens = RefreshToken.objects.filter(expires_at__lt=timezone.now())

        deleted_count, _ = tokens.delete()

        self.stdout.write(
            self.style.SUCCESS(f"Everything is ok! Deleted {deleted_count} tokens.")
        )
