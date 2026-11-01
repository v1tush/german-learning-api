from datetime import date, datetime, time

from ninja import Schema
from pydantic import Field


class ErrorOut(Schema):
    detail: str


class FixedScheduleTimeOut(Schema):
    slot: int
    local_time: time


class StudyScheduleCreateIn(Schema):
    is_enabled: bool = False
    mode: str = "interval"
    items_per_delivery: int = 1
    timezone: str = "UTC"
    interval_minutes: int | None = None
    fixed_times: list[time] = Field(default_factory=list)
    dataset_id: int | None


class StudyScheduleUpdateIn(Schema):
    is_enabled: bool | None = None
    mode: str | None = None
    items_per_delivery: int | None = None
    timezone: str | None = None
    interval_minutes: int | None = None
    fixed_times: list[time] | None = None
    dataset_id: int | None = None


class StudyScheduleOut(Schema):
    id: int
    is_enabled: bool
    mode: str
    items_per_delivery: int
    timezone: str
    interval_minutes: int | None
    next_run_at: datetime | None
    dataset_id: int | None
    fixed_times: list[FixedScheduleTimeOut]


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
    items: list[ScheduleRunItemOut]
