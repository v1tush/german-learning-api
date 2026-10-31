from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from tags.models import UserTag
from translations.choices import WordStatusChoices
from words.models import UserWord

from schedules.errors import (
    InsufficientLearningWordsError,
    InvalidScheduleConfigurationError,
    InvalidTagIdsError,
    ScheduleHasRunsError,
    ScheduleNotFoundError,
    UnsupportedDeliveryFormatError,
)
from schedules.models import FixedScheduleTime, ScheduleRun, ScheduleRunItem, StudySchedule, validate_timezone

MAX_FIXED_SCHEDULE_TIMES = 5
_MISSING = object()


def get_user_schedule(user, schedule_id: int, *, for_update: bool = False) -> StudySchedule:
    schedules = StudySchedule.objects.filter(pk=schedule_id, user=user)
    if for_update:
        schedules = schedules.select_for_update()

    schedule = schedules.first()
    if schedule is None:
        raise ScheduleNotFoundError()

    return schedule


def get_user_tags(user, tag_ids: list[int]) -> list[UserTag]:
    unique_tag_ids = set(tag_ids)
    tags = list(UserTag.objects.filter(user=user, pk__in=unique_tag_ids))

    if len(tags) != len(unique_tag_ids):
        raise InvalidTagIdsError()

    return tags


def list_user_schedules(user):
    return StudySchedule.objects.filter(user=user).prefetch_related("tags", "fixed_times")


def serialize_schedule(schedule: StudySchedule) -> dict:
    return {
        "id": schedule.id,
        "is_enabled": schedule.is_enabled,
        "mode": schedule.mode,
        "delivery_format": schedule.delivery_format,
        "items_per_delivery": schedule.items_per_delivery,
        "timezone": schedule.timezone,
        "interval_minutes": schedule.interval_minutes,
        "next_run_at": schedule.next_run_at,
        "tags": [
            {
                "id": tag.id,
                "name": tag.name,
            }
            for tag in sorted(schedule.tags.all(), key=lambda tag: (tag.name, tag.id))
        ],
        "fixed_times": [
            {
                "slot": fixed_time.slot,
                "local_time": fixed_time.local_time,
            }
            for fixed_time in schedule.fixed_times.all()
        ],
    }


def serialize_schedule_run(run: ScheduleRun) -> dict:
    items = ScheduleRunItem.objects.filter(run=run).select_related("user_word__word")

    return {
        "id": run.id,
        "schedule_id": run.schedule_id,
        "scheduled_for": run.scheduled_for,
        "status": run.status,
        "delivery_format": run.delivery_format,
        "items": [
            {
                "position": item.position,
                "local_date": item.local_date,
                "user_word": None
                if item.user_word is None
                else {
                    "id": item.user_word.id,
                    "word_id": item.user_word.word_id,
                    "word": item.user_word.word.word,
                    "language": item.user_word.word.language,
                    "part_of_speech": item.user_word.word.part_of_speech,
                    "custom_translation": item.user_word.custom_translation,
                    "user_hint": item.user_word.user_hint,
                    "status": item.user_word.status,
                },
            }
            for item in items
        ],
    }


def get_eligible_words(schedule: StudySchedule):
    words = UserWord.objects.filter(
        user_id=schedule.user_id,
        status=WordStatusChoices.LEARNING,
    )

    if schedule.tags.exists():
        words = words.filter(tags__in=schedule.tags.all()).distinct()

    return words


def validate_schedule_pool(schedule: StudySchedule) -> int:
    available_count = get_eligible_words(schedule).count()

    if available_count < schedule.items_per_delivery:
        raise InsufficientLearningWordsError()

    return available_count


def validate_schedule_configuration(
    *,
    mode: str,
    items_per_delivery: int,
    timezone_name: str,
    interval_minutes: int | None,
    fixed_times: list[time],
) -> None:
    if items_per_delivery <= 0:
        raise InvalidScheduleConfigurationError("items_per_delivery_must_be_positive")

    try:
        validate_timezone(timezone_name)
    except ValidationError as exc:
        raise InvalidScheduleConfigurationError("invalid_timezone") from exc

    if mode == StudySchedule.Mode.INTERVAL:
        if interval_minutes is None or interval_minutes <= 0:
            raise InvalidScheduleConfigurationError("interval_minutes_required")
        if fixed_times:
            raise InvalidScheduleConfigurationError("fixed_times_not_allowed_for_interval")
        return

    if mode == StudySchedule.Mode.FIXED_TIMES:
        if interval_minutes is not None:
            raise InvalidScheduleConfigurationError("interval_minutes_not_allowed_for_fixed_times")
        if not fixed_times:
            raise InvalidScheduleConfigurationError("fixed_times_required")
        if len(fixed_times) > MAX_FIXED_SCHEDULE_TIMES:
            raise InvalidScheduleConfigurationError("too_many_fixed_times")
        if len(set(fixed_times)) != len(fixed_times):
            raise InvalidScheduleConfigurationError("duplicate_fixed_times")
        return

    raise InvalidScheduleConfigurationError("invalid_schedule_mode")


def replace_fixed_times(schedule: StudySchedule, fixed_times: list[time]) -> None:
    schedule.fixed_times.all().delete()
    FixedScheduleTime.objects.bulk_create(
        [
            FixedScheduleTime(
                schedule=schedule,
                slot=slot,
                local_time=local_time,
            )
            for slot, local_time in enumerate(sorted(fixed_times), start=1)
        ]
    )


def calculate_next_run_at(
    schedule: StudySchedule,
    reference_at: datetime | None = None,
) -> datetime:
    reference_at = reference_at or timezone.now()
    if timezone.is_naive(reference_at):
        raise ValueError("reference_at_must_be_timezone_aware")

    fixed_times = list(schedule.fixed_times.values_list("local_time", flat=True))
    validate_schedule_configuration(
        mode=schedule.mode,
        items_per_delivery=schedule.items_per_delivery,
        timezone_name=schedule.timezone,
        interval_minutes=schedule.interval_minutes,
        fixed_times=fixed_times,
    )

    if schedule.mode == StudySchedule.Mode.INTERVAL:
        return reference_at + timedelta(minutes=schedule.interval_minutes)

    schedule_timezone = ZoneInfo(schedule.timezone)
    local_reference_at = timezone.localtime(reference_at, schedule_timezone)
    local_times = sorted(fixed_times)

    for day_offset in range(2):
        local_date = local_reference_at.date() + timedelta(days=day_offset)
        for local_time in local_times:
            candidate = datetime.combine(local_date, local_time, tzinfo=schedule_timezone)
            candidate = candidate.astimezone(UTC)
            if candidate > reference_at:
                return candidate

    raise RuntimeError("could_not_calculate_next_run_at")


def create_study_schedule(
    user,
    *,
    is_enabled: bool,
    mode: str,
    items_per_delivery: int,
    timezone_name: str,
    interval_minutes: int | None,
    fixed_times: list[time],
    tag_ids: list[int],
) -> StudySchedule:
    tags = get_user_tags(user, tag_ids)
    validate_schedule_configuration(
        mode=mode,
        items_per_delivery=items_per_delivery,
        timezone_name=timezone_name,
        interval_minutes=interval_minutes,
        fixed_times=fixed_times,
    )

    with transaction.atomic():
        schedule = StudySchedule.objects.create(
            user=user,
            is_enabled=is_enabled,
            mode=mode,
            delivery_format=StudySchedule.DeliveryFormat.WORDS,
            items_per_delivery=items_per_delivery,
            timezone=timezone_name,
            interval_minutes=interval_minutes,
        )
        schedule.tags.set(tags)
        replace_fixed_times(schedule, fixed_times)
        validate_schedule_pool(schedule)

        if schedule.is_enabled:
            schedule.next_run_at = calculate_next_run_at(schedule)
            schedule.save(update_fields=["next_run_at", "updated_at"])

    return schedule


def update_study_schedule(user, schedule_id: int, payload: dict) -> StudySchedule:
    for field in ("is_enabled", "mode", "items_per_delivery", "timezone", "fixed_times", "tags"):
        if field in payload and payload[field] is None:
            raise InvalidScheduleConfigurationError(f"{field}_cannot_be_null")

    tags = get_user_tags(user, payload["tags"]) if "tags" in payload else None

    with transaction.atomic():
        schedule = get_user_schedule(user, schedule_id, for_update=True)

        was_enabled = schedule.is_enabled
        previous_mode = schedule.mode
        previous_timezone = schedule.timezone
        previous_interval_minutes = schedule.interval_minutes
        mode = payload.get("mode", schedule.mode)
        items_per_delivery = payload.get("items_per_delivery", schedule.items_per_delivery)
        timezone_name = payload.get("timezone", schedule.timezone)
        is_enabled = payload.get("is_enabled", schedule.is_enabled)
        existing_fixed_times = list(schedule.fixed_times.values_list("local_time", flat=True))
        interval_value = payload.get("interval_minutes", _MISSING)

        if mode == StudySchedule.Mode.INTERVAL:
            interval_minutes = schedule.interval_minutes if interval_value is _MISSING else interval_value
            fixed_times = []
            if payload.get("fixed_times"):
                raise InvalidScheduleConfigurationError("fixed_times_not_allowed_for_interval")
        elif mode == StudySchedule.Mode.FIXED_TIMES:
            if interval_value is not _MISSING and interval_value is not None:
                raise InvalidScheduleConfigurationError("interval_minutes_not_allowed_for_fixed_times")
            interval_minutes = None
            fixed_times = payload.get("fixed_times", existing_fixed_times)
        else:
            interval_minutes = schedule.interval_minutes if interval_value is _MISSING else interval_value
            fixed_times = payload.get("fixed_times", existing_fixed_times)

        validate_schedule_configuration(
            mode=mode,
            items_per_delivery=items_per_delivery,
            timezone_name=timezone_name,
            interval_minutes=interval_minutes,
            fixed_times=fixed_times,
        )

        schedule.is_enabled = is_enabled
        schedule.mode = mode
        schedule.items_per_delivery = items_per_delivery
        schedule.timezone = timezone_name
        schedule.interval_minutes = interval_minutes
        schedule.save()

        if tags is not None:
            schedule.tags.set(tags)

        if mode == StudySchedule.Mode.INTERVAL or "fixed_times" in payload:
            replace_fixed_times(schedule, fixed_times)

        validate_schedule_pool(schedule)

        timing_changed = (
            mode != previous_mode
            or timezone_name != previous_timezone
            or interval_minutes != previous_interval_minutes
            or "fixed_times" in payload
        )
        if not schedule.is_enabled:
            schedule.next_run_at = None
        elif not was_enabled or timing_changed or schedule.next_run_at is None:
            schedule.next_run_at = calculate_next_run_at(schedule)
        else:
            return schedule

        schedule.save(update_fields=["next_run_at", "updated_at"])

    return schedule


def delete_study_schedule(user, schedule_id: int) -> None:
    with transaction.atomic():
        schedule = get_user_schedule(user, schedule_id, for_update=True)

        try:
            schedule.delete()
        except ProtectedError as exc:
            raise ScheduleHasRunsError() from exc


def select_words_for_schedule(schedule: StudySchedule) -> list[UserWord]:
    validate_schedule_pool(schedule)

    previously_selected_word_ids = ScheduleRunItem.objects.filter(
        schedule=schedule,
        run__status__in=[ScheduleRun.Status.PENDING, ScheduleRun.Status.SENT],
        user_word__isnull=False,
    ).values("user_word_id")

    new_words = list(
        get_eligible_words(schedule)
        .exclude(pk__in=previously_selected_word_ids)
        .order_by("?")[: schedule.items_per_delivery]
    )

    remaining_count = schedule.items_per_delivery - len(new_words)
    if remaining_count == 0:
        return new_words

    repeated_words = list(
        get_eligible_words(schedule)
        .filter(pk__in=previously_selected_word_ids)
        .exclude(pk__in=[word.pk for word in new_words])
        .order_by("?")[:remaining_count]
    )

    selected_words = new_words + repeated_words
    if len(selected_words) != schedule.items_per_delivery:
        raise RuntimeError("could_not_select_required_number_of_words")

    return selected_words


def create_schedule_run(schedule_id: int, scheduled_for: datetime | None = None) -> ScheduleRun:
    scheduled_for = scheduled_for or timezone.now()

    if timezone.is_naive(scheduled_for):
        raise ValueError("scheduled_for_must_be_timezone_aware")

    with transaction.atomic():
        schedule = StudySchedule.objects.select_for_update().get(pk=schedule_id)

        if schedule.delivery_format != StudySchedule.DeliveryFormat.WORDS:
            raise UnsupportedDeliveryFormatError()

        existing_run = ScheduleRun.objects.filter(
            schedule=schedule,
            scheduled_for=scheduled_for,
        ).first()
        if existing_run is not None:
            return existing_run

        selected_words = select_words_for_schedule(schedule)
        local_date = timezone.localtime(scheduled_for, ZoneInfo(schedule.timezone)).date()
        run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=scheduled_for,
            delivery_format=schedule.delivery_format,
        )
        ScheduleRunItem.objects.bulk_create(
            [
                ScheduleRunItem(
                    run=run,
                    schedule=schedule,
                    user_word=user_word,
                    position=position,
                    local_date=local_date,
                )
                for position, user_word in enumerate(selected_words, start=1)
            ]
        )

    return run


def create_schedule_run_for_user(user, schedule_id: int) -> ScheduleRun:
    schedule = get_user_schedule(user, schedule_id)
    return create_schedule_run(schedule.pk)
