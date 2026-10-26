from core.models import TimeStampedModel
from django.contrib.auth import get_user_model
from django.db import models
from words.choices import LanguageChoices
from words.models import Word

from translations.choices import WordStatusChoices

User = get_user_model()


class BaseTranslation(TimeStampedModel):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="base_translations")
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


class UserTag(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags", db_index=False)
    name = models.CharField(max_length=50)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_user_tag")]
        verbose_name = "User Tag"
        verbose_name_plural = "User Tags"

    def __str__(self):
        return f"{self.name} (User: {self.user.username})"


class UserWord(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vocabulary", db_index=False)
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="user_links", db_index=False)
    custom_translation = models.CharField(max_length=500, blank=True, null=True)
    user_hint = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(UserTag, blank=True, related_name="user_words")
    status = models.CharField(max_length=20, choices=WordStatusChoices, default=WordStatusChoices.LEARNING)
    last_sent_at = models.DateTimeField(blank=True, null=True)
    selected_translation = models.ForeignKey(
        BaseTranslation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_selections",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "word"], name="unique_user_word")]
        verbose_name = "User Word"
        verbose_name_plural = "User Words"
