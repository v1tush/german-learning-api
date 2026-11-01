import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from datasets.models import UserDataset
from datasets.services import get_dataset_words
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from translations.choices import WordStatusChoices
from words.choices import InflectionTypeChoices
from words.models import UserWord

from schedules.errors import (
    InsufficientLearningWordsError,
    InvalidDatasetIdError,
    InvalidScheduleConfigurationError,
    ScheduleHasRunsError,
    ScheduleNotFoundError,
)
from schedules.models import (
    FixedScheduleTime,
    ScheduleRun,
    ScheduleRunItem,
    SiteNotification,
    StudySchedule,
    validate_timezone,
)

MAX_FIXED_SCHEDULE_TIMES = 5
_MISSING = object()
logger = logging.getLogger(__name__)


def get_user_schedule(user, schedule_id: int, *, for_update: bool = False) -> StudySchedule:
    schedules = StudySchedule.objects.filter(pk=schedule_id, user=user)
    if for_update:
        schedules = schedules.select_for_update()

    schedule = schedules.first()
    if schedule is None:
        raise ScheduleNotFoundError()

    return schedule


def get_user_dataset(user, dataset_id: int | None) -> UserDataset | None:
    if dataset_id is None:
        return None

    dataset = UserDataset.objects.filter(user=user, pk=dataset_id).first()
    if dataset is None:
        raise InvalidDatasetIdError()

    return dataset


def list_user_schedules(user):
    return StudySchedule.objects.filter(user=user).prefetch_related("fixed_times")


def serialize_schedule(schedule: StudySchedule) -> dict:
    return {
        "id": schedule.id,
        "is_enabled": schedule.is_enabled,
        "mode": schedule.mode,
        "exercise_kind": schedule.exercise_kind,
        "inflection_type": schedule.inflection_type,
        "items_per_delivery": schedule.items_per_delivery,
        "timezone": schedule.timezone,
        "interval_minutes": schedule.interval_minutes,
        "next_run_at": schedule.next_run_at,
        "dataset_id": schedule.dataset_id,
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
        "exercise_kind": run.exercise_kind,
        "inflection_type": run.inflection_type,
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


def get_schedule_dataset_words(schedule: StudySchedule):
    if schedule.dataset_id is None:
        return UserWord.objects.filter(user_id=schedule.user_id)

    return UserWord.objects.filter(
        pk__in=get_dataset_words(schedule.dataset).values("pk"),
        user_id=schedule.user_id,
    )


def get_eligible_words(schedule: StudySchedule):
    words = get_schedule_dataset_words(schedule).filter(status=WordStatusChoices.LEARNING)
    if schedule.exercise_kind == StudySchedule.ExerciseKind.INFLECTION:
        words = words.filter(
            word__inflections__type=schedule.inflection_type,
            word__inflections__value__gt="",
        )
    return words


def validate_schedule_pool(schedule: StudySchedule) -> int:
    available_count = get_eligible_words(schedule).count()

    if available_count < schedule.items_per_delivery:
        raise InsufficientLearningWordsError()

    return available_count


def validate_exercise_configuration(exercise_kind: str, inflection_type: str | None) -> None:
    if exercise_kind == StudySchedule.ExerciseKind.TRANSLATION:
        if inflection_type is not None:
            raise InvalidScheduleConfigurationError("inflection_type_not_allowed_for_translation")
        return
    if exercise_kind == StudySchedule.ExerciseKind.INFLECTION:
        if inflection_type not in InflectionTypeChoices.values:
            raise InvalidScheduleConfigurationError("invalid_inflection_type")
        return
    raise InvalidScheduleConfigurationError("invalid_exercise_kind")


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
    exercise_kind: str,
    inflection_type: str | None,
    items_per_delivery: int,
    timezone_name: str,
    interval_minutes: int | None,
    fixed_times: list[time],
    dataset_id: int | None,
) -> StudySchedule:
    dataset = get_user_dataset(user, dataset_id)
    validate_schedule_configuration(
        mode=mode,
        items_per_delivery=items_per_delivery,
        timezone_name=timezone_name,
        interval_minutes=interval_minutes,
        fixed_times=fixed_times,
    )
    validate_exercise_configuration(exercise_kind, inflection_type)

    with transaction.atomic():
        schedule = StudySchedule.objects.create(
            user=user,
            is_enabled=is_enabled,
            mode=mode,
            exercise_kind=exercise_kind,
            inflection_type=inflection_type,
            items_per_delivery=items_per_delivery,
            timezone=timezone_name,
            interval_minutes=interval_minutes,
            dataset=dataset,
        )
        replace_fixed_times(schedule, fixed_times)
        validate_schedule_pool(schedule)
        if schedule.is_enabled:
            schedule.next_run_at = calculate_next_run_at(schedule)
            schedule.save(update_fields=["next_run_at", "updated_at"])

    return schedule


def update_study_schedule(user, schedule_id: int, payload: dict) -> StudySchedule:
    for field in ("is_enabled", "mode", "exercise_kind", "items_per_delivery", "timezone", "fixed_times"):
        if field in payload and payload[field] is None:
            raise InvalidScheduleConfigurationError(f"{field}_cannot_be_null")

    dataset = get_user_dataset(user, payload["dataset_id"]) if "dataset_id" in payload else _MISSING

    with transaction.atomic():
        schedule = get_user_schedule(user, schedule_id, for_update=True)

        was_enabled = schedule.is_enabled
        previous_mode = schedule.mode
        previous_timezone = schedule.timezone
        previous_interval_minutes = schedule.interval_minutes
        mode = payload.get("mode", schedule.mode)
        exercise_kind = payload.get("exercise_kind", schedule.exercise_kind)
        inflection_type = payload.get("inflection_type", schedule.inflection_type)
        if exercise_kind == StudySchedule.ExerciseKind.TRANSLATION and "inflection_type" not in payload:
            inflection_type = None
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
        validate_exercise_configuration(exercise_kind, inflection_type)

        schedule.is_enabled = is_enabled
        schedule.mode = mode
        schedule.exercise_kind = exercise_kind
        schedule.inflection_type = inflection_type
        schedule.items_per_delivery = items_per_delivery
        schedule.timezone = timezone_name
        schedule.interval_minutes = interval_minutes
        if dataset is not _MISSING:
            schedule.dataset = dataset
        schedule.save()

        if mode == StudySchedule.Mode.INTERVAL or "fixed_times" in payload:
            replace_fixed_times(schedule, fixed_times)

        if schedule.is_enabled:
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


def select_words_for_schedule(schedule: StudySchedule, *, local_date: date) -> list[UserWord]:
    validate_schedule_pool(schedule)

    previously_selected_word_ids = ScheduleRunItem.objects.filter(
        schedule=schedule,
        run__exercise_kind=schedule.exercise_kind,
        run__inflection_type=schedule.inflection_type,
        user_word__isnull=False,
    ).values("user_word_id")
    selected_today_word_ids = ScheduleRunItem.objects.filter(
        schedule=schedule,
        local_date=local_date,
        run__exercise_kind=schedule.exercise_kind,
        run__inflection_type=schedule.inflection_type,
        user_word__isnull=False,
    ).values("user_word_id")

    eligible_words = get_eligible_words(schedule)
    word_pools = (
        eligible_words.exclude(pk__in=previously_selected_word_ids),
        eligible_words.filter(pk__in=previously_selected_word_ids).exclude(pk__in=selected_today_word_ids),
        eligible_words.filter(pk__in=selected_today_word_ids),
    )
    selected_words = []
    for pool in word_pools:
        remaining_count = schedule.items_per_delivery - len(selected_words)
        if remaining_count == 0:
            break
        selected_words.extend(pool.exclude(pk__in=[word.pk for word in selected_words]).order_by("?")[:remaining_count])

    if len(selected_words) != schedule.items_per_delivery:
        raise InsufficientLearningWordsError()

    return selected_words


def create_schedule_run(schedule_id: int, scheduled_for: datetime | None = None) -> ScheduleRun:
    scheduled_for = scheduled_for or timezone.now()

    if timezone.is_naive(scheduled_for):
        raise ValueError("scheduled_for_must_be_timezone_aware")

    with transaction.atomic():
        schedule = StudySchedule.objects.select_for_update().get(pk=schedule_id)
        return _create_schedule_run_locked(schedule, scheduled_for)


def create_due_schedule_run(schedule_id: int, *, now: datetime | None = None) -> ScheduleRun | None:
    now = now or timezone.now()
    if timezone.is_naive(now):
        raise ValueError("now_must_be_timezone_aware")

    with transaction.atomic():
        schedule = StudySchedule.objects.select_for_update().filter(pk=schedule_id).first()
        if schedule is None or not schedule.is_enabled or schedule.next_run_at is None:
            return None
        if schedule.next_run_at > now:
            return None

        scheduled_for = schedule.next_run_at
        try:
            run = _create_schedule_run_locked(schedule, scheduled_for)
        except InsufficientLearningWordsError:
            run = None
            logger.warning(
                "Schedule %s skipped due slot %s: fewer learning words than items_per_delivery",
                schedule.pk,
                scheduled_for,
            )

        if schedule.mode == StudySchedule.Mode.INTERVAL:
            interval = timedelta(minutes=schedule.interval_minutes)
            elapsed_intervals = (now - scheduled_for) // interval
            schedule.next_run_at = scheduled_for + interval * (elapsed_intervals + 1)
        else:
            schedule.next_run_at = calculate_next_run_at(schedule, reference_at=now)
        schedule.save(update_fields=["next_run_at", "updated_at"])

        return run


def _create_schedule_run_locked(schedule: StudySchedule, scheduled_for: datetime) -> ScheduleRun:
    existing_run = ScheduleRun.objects.filter(
        schedule=schedule,
        scheduled_for=scheduled_for,
    ).first()
    if existing_run is not None:
        return existing_run

    local_date = timezone.localtime(scheduled_for, ZoneInfo(schedule.timezone)).date()
    selected_words = select_words_for_schedule(schedule, local_date=local_date)
    run = ScheduleRun.objects.create(
        schedule=schedule,
        scheduled_for=scheduled_for,
        exercise_kind=schedule.exercise_kind,
        inflection_type=schedule.inflection_type,
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
    SiteNotification.objects.create(run=run)

    return run


def create_schedule_run_for_user(user, schedule_id: int) -> ScheduleRun:
    schedule = get_user_schedule(user, schedule_id)
    return create_schedule_run(schedule.pk)
