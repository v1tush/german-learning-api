from datetime import date, datetime

from ninja import Schema


class ErrorOut(Schema):
    detail: str


class ScheduleRunWordOut(Schema):
    id: int
    word_id: int
    word: str
    language: str
    part_of_speech: str
    custom_translation: str | None
    user_hint: str | None
    status: str


class ScheduleRunItemOut(Schema):
    position: int
    local_date: date
    user_word: ScheduleRunWordOut | None


class ScheduleRunOut(Schema):
    id: int
    schedule_id: int
    scheduled_for: datetime
    status: str
    delivery_format: str
    items: list[ScheduleRunItemOut]
