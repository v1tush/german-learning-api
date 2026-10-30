from ninja import ModelSchema
from pydantic import Field
from translations.choices import WordStatusChoices

from words.models import UserWord, Word


class WordIn(ModelSchema):
    class Meta:
        model = Word
        fields = ["word", "language", "part_of_speech"]


class WordOut(ModelSchema):
    class Meta:
        model = Word
        fields = ["id", "word", "language", "part_of_speech"]


class UserWordIn(ModelSchema):
    tags: list[int] = Field(default_factory=list)
    status: WordStatusChoices = WordStatusChoices.LEARNING

    class Meta:
        model = UserWord
        fields = ["word", "custom_translation", "user_hint", "tags", "status", "selected_translation"]


class UserWordUpdate(ModelSchema):
    status: WordStatusChoices | None = None

    class Meta:
        model = UserWord
        fields = ["custom_translation", "user_hint", "tags", "status", "selected_translation"]
        fields_optional = "__all__"


class UserWordOut(ModelSchema):
    class Meta:
        model = UserWord
        fields = [
            "id",
            "word",
            "custom_translation",
            "user_hint",
            "tags",
            "status",
            "selected_translation",
            "created_at",
            "updated_at",
        ]
