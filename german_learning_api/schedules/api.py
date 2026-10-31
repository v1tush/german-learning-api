from authentication.auth import GlobalAuth
from ninja import Router
from ninja.errors import HttpError

from schedules.models import ScheduleRunItem, StudySchedule
from schedules.schemas import ErrorOut, ScheduleRunOut
from schedules.services import (
    InsufficientLearningWordsError,
    UnsupportedDeliveryFormatError,
    create_schedule_run,
)

schedules_router = Router(auth=GlobalAuth())


@schedules_router.post(
    "/{schedule_id}/runs",
    response={
        201: ScheduleRunOut,
        401: ErrorOut,
        404: ErrorOut,
        422: ErrorOut,
    },
)
def create_run(request, schedule_id: int):
    schedule = StudySchedule.objects.filter(
        pk=schedule_id,
        user=request.auth,
    ).first()
    if schedule is None:
        raise HttpError(404, "schedule_not_found")

    try:
        run = create_schedule_run(schedule.pk)
    except InsufficientLearningWordsError as exc:
        raise HttpError(422, "insufficient_learning_words") from exc
    except UnsupportedDeliveryFormatError as exc:
        raise HttpError(422, "word_delivery_format_required") from exc

    items = ScheduleRunItem.objects.filter(run=run).select_related("user_word__word")

    return 201, {
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
