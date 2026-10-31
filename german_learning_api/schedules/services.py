from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from translations.choices import WordStatusChoices
from words.models import UserWord

from schedules.models import ScheduleRun, ScheduleRunItem, StudySchedule


class InsufficientLearningWordsError(Exception):
    def __init__(self, available_count: int, required_count: int):
        self.available_count = available_count
        self.required_count = required_count
        super().__init__("insufficient_learning_words")


class UnsupportedDeliveryFormatError(Exception):
    pass


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
        raise InsufficientLearningWordsError(
            available_count=available_count,
            required_count=schedule.items_per_delivery,
        )

    return available_count


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
            raise UnsupportedDeliveryFormatError

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
