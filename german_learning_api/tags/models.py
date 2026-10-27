from django.contrib.auth import get_user_model
from django.db import models

from core.models import TimeStampedModel


User = get_user_model()


class UserTag(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags", db_index=False)
    name = models.CharField(max_length=50)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_user_tag")]
        verbose_name = "User Tag"
        verbose_name_plural = "User Tags"

    def __str__(self):
        return f"{self.name} (User: {self.user.username})"