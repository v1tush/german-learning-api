from datetime import datetime
from typing import Literal

from ninja import ModelSchema, Schema
from pydantic import Field, field_validator
from translations.choices import WordStatusChoices

from words.choices import InflectionTypeChoices
from words.models import UserWord, Word


class WordIn(ModelSchema):
    class Meta:
        model = Word
        fields = ["word", "language", "part_of_speech"]


class WordOut(ModelSchema):
    class Meta:
        model = Word
        fields = ["id", "word", "language", "part_of_speech"]


class WordPageOut(Schema):
    page: int
    sort: Literal["id", "popular"]
    page_size: int
    words: list[WordOut]
    has_next: bool


class WordInflectionIn(Schema):
    type: InflectionTypeChoices
    value: str = Field(max_length=255)

    @field_validator("value")
    @classmethod
    def nonempty_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("inflection_value_required")
        return value


class WordInflectionUpdate(Schema):
    type: InflectionTypeChoices | None = None
    value: str | None = Field(default=None, max_length=255)

    @field_validator("value")
    @classmethod
    def nonempty_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("inflection_value_required")
        return value


class WordInflectionOut(Schema):
    id: int
    word_id: int
    type: str
    value: str
    created_at: datetime
    updated_at: datetime


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
