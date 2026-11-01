from datetime import datetime

from ninja import Schema
from pydantic import Field


class ErrorOut(Schema):
    detail: str


class DatasetCreateIn(Schema):
    name: str
    tags: list[int] = Field(default_factory=list)
    extra_words: list[int] = Field(default_factory=list)


class DatasetUpdateIn(Schema):
    name: str | None = None
    tags: list[int] | None = None
    extra_words: list[int] | None = None


class DatasetOut(Schema):
    id: int
    name: str
    tags: list[int]
    extra_words: list[int]
    created_at: datetime
    updated_at: datetime


class DatasetWordOut(Schema):
    id: int
    word_id: int
    word: str
    language: str
    part_of_speech: str
    custom_translation: str | None
    user_hint: str | None
    status: str
