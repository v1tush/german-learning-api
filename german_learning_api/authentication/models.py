from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class RefreshToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    token = models.UUIDField(unique=True, editable=False)
    used = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def save(self, **kwargs):
        if not self.pk:
            self.expires_at = timezone.now() + timedelta(seconds=settings.REFRESH_TIME)
        super().save(**kwargs)

    @property
    def is_active(self):
        return not self.used and not self.revoked
