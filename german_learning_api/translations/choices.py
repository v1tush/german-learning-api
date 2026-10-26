from django.db import models


class WordStatusChoices(models.TextChoices):
    LEARNING = "learning", "Learning"
    MASTERED = "mastered", "Mastered"
    PAUSED = "paused", "Paused"
