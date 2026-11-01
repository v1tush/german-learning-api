from core.models import TimeStampedModel
from django.conf import settings
from django.db import models


class UserDataset(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="datasets")
    name = models.CharField(max_length=100)
    tags = models.ManyToManyField("tags.UserTag", blank=True, related_name="datasets")
    extra_words = models.ManyToManyField("words.UserWord", blank=True, related_name="datasets_as_extra")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_user_dataset_name")]
        verbose_name = "User Dataset"
        verbose_name_plural = "User Datasets"

    def __str__(self) -> str:
        return f"{self.name} (User: {self.user_id})"
