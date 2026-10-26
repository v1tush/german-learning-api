from core.models import TimeStampedModel
from django.db import models

from words.choices import InflectionTypeChoices, LanguageChoices, PartOfSpeechChoices


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
