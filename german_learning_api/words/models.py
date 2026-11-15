from core.models import TimeStampedModel
from django.contrib.auth import get_user_model
from django.db import models
from tags.models import UserTag
from translations.choices import WordStatusChoices

from words.choices import InflectionTypeChoices, LanguageChoices, PartOfSpeechChoices

User = get_user_model()


class Word(TimeStampedModel):
    word = models.CharField(max_length=255, db_index=True)
    language = models.CharField(max_length=10, choices=LanguageChoices, default=LanguageChoices.GERMAN)
    part_of_speech = models.CharField(max_length=20, choices=PartOfSpeechChoices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["word", "language", "part_of_speech"], name="unique_word_lang_pos")
        ]
        verbose_name = "Global Word"
        verbose_name_plural = "Global Words"

    def __str__(self):
        return f"{self.word} ({self.language}) [{self.part_of_speech}]"


class WordProperties(TimeStampedModel):
    word = models.OneToOneField(Word, on_delete=models.CASCADE, related_name="properties")
    transcription = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Word Property"
        verbose_name_plural = "Word Properties"


class WordInflection(TimeStampedModel):
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="inflections")
    type = models.CharField(max_length=30, choices=InflectionTypeChoices)
    value = models.CharField(max_length=255, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["word", "type"], name="unique_word_inflection_type")]
        verbose_name = "Word Inflection"
        verbose_name_plural = "Word Inflections"


class UserWord(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vocabulary", db_index=False)
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="user_links", db_index=False)
    user_hint = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(UserTag, blank=True, related_name="user_words")
    status = models.CharField(max_length=20, choices=WordStatusChoices, default=WordStatusChoices.LEARNING)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "word"], name="unique_user_word")]
        indexes = [models.Index(fields=["word"], name="userword_word_idx")]
        verbose_name = "User Word"
        verbose_name_plural = "User Words"


class UserWordTranslation(TimeStampedModel):
    user_word = models.ForeignKey(UserWord, on_delete=models.CASCADE, related_name="translations")
    target_language = models.CharField(max_length=10, choices=LanguageChoices)
    base_translation = models.ForeignKey(
        "translations.BaseTranslation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_selections",
    )
    custom_translation = models.CharField(max_length=500, null=True, blank=True)
    is_card_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(base_translation__isnull=False, custom_translation__isnull=True)
                    | (
                        models.Q(base_translation__isnull=True, custom_translation__isnull=False)
                        & ~models.Q(custom_translation="")
                    )
                ),
                name="user_word_translation_one_source",
            ),
            models.UniqueConstraint(
                fields=["user_word", "base_translation"],
                condition=models.Q(base_translation__isnull=False),
                name="unique_user_word_base_translation",
            ),
            models.UniqueConstraint(
                fields=["user_word", "target_language"],
                condition=models.Q(base_translation__isnull=True),
                name="unique_user_word_custom_per_language",
            ),
        ]
        ordering = ["id"]
