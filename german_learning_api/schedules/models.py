from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.models import TimeStampedModel
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError("invalid_timezone") from exc


class StudySchedule(TimeStampedModel):
    class Mode(models.TextChoices):
        INTERVAL = "interval", "Interval"
        FIXED_TIMES = "fixed_times", "Fixed times"

    class DeliveryFormat(models.TextChoices):
        WORDS = "words", "Words"
        SESSION = "session", "Session"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_schedules",
    )
    is_enabled = models.BooleanField(default=False)
    mode = models.CharField(max_length=16, choices=Mode, default=Mode.INTERVAL)
    delivery_format = models.CharField(
        max_length=16,
        choices=DeliveryFormat,
        default=DeliveryFormat.WORDS,
    )
    items_per_delivery = models.PositiveSmallIntegerField(default=1)
    timezone = models.CharField(max_length=63, default="UTC", validators=[validate_timezone])
    interval_minutes = models.PositiveIntegerField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField("tags.UserTag", related_name="study_schedules")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(items_per_delivery__gt=0),
                name="schedule_items_per_delivery_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        mode="interval",
                        interval_minutes__isnull=False,
                        interval_minutes__gt=0,
                    )
                    | models.Q(mode="fixed_times", interval_minutes__isnull=True)
                ),
                name="schedule_mode_interval_configuration",
            ),
        ]
        indexes = [models.Index(fields=["is_enabled", "next_run_at"])]

    def __str__(self) -> str:
        return f"Study schedule {self.pk} for user {self.user_id}"


class FixedScheduleTime(TimeStampedModel):
    schedule = models.ForeignKey(
        StudySchedule,
        on_delete=models.CASCADE,
        related_name="fixed_times",
    )
    slot = models.PositiveSmallIntegerField()
    local_time = models.TimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(slot__gte=1, slot__lte=5),
                name="fixed_schedule_time_slot_range",
            ),
            models.UniqueConstraint(
                fields=["schedule", "slot"],
                name="unique_fixed_schedule_time_slot",
            ),
            models.UniqueConstraint(
                fields=["schedule", "local_time"],
                name="unique_fixed_schedule_local_time",
            ),
        ]
        ordering = ["slot"]


class ScheduleRun(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    schedule = models.ForeignKey(
        StudySchedule,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    delivery_format = models.CharField(max_length=16, choices=StudySchedule.DeliveryFormat)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "scheduled_for"],
                name="unique_schedule_run_moment",
            ),
        ]
        indexes = [models.Index(fields=["status", "scheduled_for"])]
        ordering = ["-scheduled_for"]


class ScheduleRunItem(TimeStampedModel):
    run = models.ForeignKey(
        ScheduleRun,
        on_delete=models.CASCADE,
        related_name="items",
    )
    schedule = models.ForeignKey(
        StudySchedule,
        on_delete=models.PROTECT,
        related_name="run_items",
    )
    user_word = models.ForeignKey(
        "words.UserWord",
        on_delete=models.SET_NULL,
        null=True,
        related_name="schedule_run_items",
    )
    position = models.PositiveSmallIntegerField()
    local_date = models.DateField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(position__gt=0),
                name="schedule_run_item_position_positive",
            ),
            models.UniqueConstraint(
                fields=["run", "position"],
                name="unique_schedule_run_item_position",
            ),
            models.UniqueConstraint(
                fields=["run", "user_word"],
                name="unique_schedule_run_user_word",
            ),
            models.UniqueConstraint(
                fields=["schedule", "local_date", "user_word"],
                name="unique_schedule_daily_user_word",
            ),
        ]
        ordering = ["position"]
