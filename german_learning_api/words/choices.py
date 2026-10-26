from django.db import models


class LanguageChoices(models.TextChoices):
    ENGLISH = "en", "English"
    GERMAN = "de", "German"
    RUSSIAN = "ru", "Russian"


class PartOfSpeechChoices(models.TextChoices):
    NOUN = "noun", "Noun"
    VERB = "verb", "Verb"
    ADJECTIVE = "adj", "Adjective"
    ADVERB = "adv", "Adverb"


class InflectionTypeChoices(models.TextChoices):
    DE_PRATERITUM = "de_prateritum", "German: Präteritum"
    DE_PARTIZIP_2 = "de_partizip_2", "German: Partizip II"
    DE_PLURAL = "de_plural", "German: Plural"

    EN_PAST_SIMPLE = "en_past_simple", "English: Past Simple"
    EN_PAST_PARTICIPLE = "en_past_participle", "English: Past Participle"
    EN_GERUND = "en_gerund", "English: Gerund (-ing)"
