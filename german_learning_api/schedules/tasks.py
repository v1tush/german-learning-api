from celery import shared_task
from django.utils import timezone

from schedules.models import StudySchedule
from schedules.services import create_due_schedule_run


@shared_task(ignore_result=True)
def dispatch_due_schedules() -> None:
    due_schedule_ids = (
        StudySchedule.objects.filter(
            is_enabled=True,
            next_run_at__lte=timezone.now(),
        )
        .order_by("next_run_at", "pk")
        .values_list("pk", flat=True)
    )
    for schedule_id in due_schedule_ids.iterator(chunk_size=500):
        process_due_schedule.delay(schedule_id)


@shared_task(ignore_result=True)
def process_due_schedule(schedule_id: int) -> None:
    create_due_schedule_run(schedule_id)
