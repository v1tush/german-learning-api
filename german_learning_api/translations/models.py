from core.models import TimeStampedModel
from django.contrib.auth import get_user_model
from django.db import models

from words.choices import LanguageChoices

User = get_user_model()


class BaseTranslation(TimeStampedModel):
    word = models.ForeignKey("words.Word", on_delete=models.CASCADE, related_name="base_translations")
    translation = models.CharField(max_length=255)
    is_main = models.BooleanField(default=False)
    target_language = models.CharField(max_length=10, choices=LanguageChoices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["word", "target_language"],
                condition=models.Q(is_main=True),
                name="unique_main_translation_per_language",
            )
        ]
        verbose_name = "Base Translation"
        verbose_name_plural = "Base Translations"
