import logging

from authentication.auth import BotAuth, GlobalAuth
from ninja import Router
from ninja.errors import HttpError
from translations.services import TranslationUnavailableError, ensure_main_translation
from words.models import Word

from schedules.cards import list_schedule_cards
from schedules.errors import ScheduleError
from schedules.schemas import (
    ErrorOut,
    ReviewCardOut,
    ScheduleRunOut,
    StudyScheduleCreateIn,
    StudyScheduleOut,
    StudyScheduleUpdateIn,
)
from schedules.services import (
    create_schedule_run_for_user,
    create_study_schedule,
    delete_study_schedule,
    get_user_schedule,
    list_user_schedules,
    serialize_schedule,
    serialize_schedule_run,
    update_study_schedule,
)

schedules_router = Router(auth=[GlobalAuth(), BotAuth()])
logger = logging.getLogger(__name__)


def raise_service_error(error: ScheduleError) -> None:
    raise HttpError(error.status_code, str(error) or error.code) from error


@schedules_router.post(
    "/",
    response={
        201: StudyScheduleOut,
        400: ErrorOut,
        401: ErrorOut,
        422: ErrorOut,
    },
)
def create_schedule(request, data: StudyScheduleCreateIn):
    try:
        schedule = create_study_schedule(
            request.auth,
            is_enabled=data.is_enabled,
            mode=data.mode,
            exercise_kind=data.exercise_kind,
            inflection_type=data.inflection_type,
            items_per_delivery=data.items_per_delivery,
            timezone_name=data.timezone,
            interval_minutes=data.interval_minutes,
            fixed_times=data.fixed_times,
            dataset_id=data.dataset_id,
        )
    except ScheduleError as error:
        raise_service_error(error)

    return 201, serialize_schedule(schedule)


@schedules_router.get(
    "/",
    response={
        200: list[StudyScheduleOut],
        401: ErrorOut,
    },
)
def list_schedules(request):
    schedules = list_user_schedules(request.auth)
    return 200, [serialize_schedule(schedule) for schedule in schedules]


@schedules_router.get(
    "/{schedule_id}",
    response={
        200: StudyScheduleOut,
        401: ErrorOut,
        404: ErrorOut,
    },
)
def get_schedule(request, schedule_id: int):
    try:
        schedule = get_user_schedule(request.auth, schedule_id)
    except ScheduleError as error:
        raise_service_error(error)

    return 200, serialize_schedule(schedule)


@schedules_router.get("/{schedule_id}/cards", response={200: list[ReviewCardOut], 401: ErrorOut, 404: ErrorOut})
def get_schedule_cards(request, schedule_id: int):
    try:
        schedule = get_user_schedule(request.auth, schedule_id)
    except ScheduleError as error:
        raise_service_error(error)
    return 200, list_schedule_cards(schedule)


@schedules_router.post(
    "/{schedule_id}/cards/{user_word_id}/resolve-answer",
    response={200: ReviewCardOut, 404: ErrorOut, 422: ErrorOut, 502: ErrorOut},
)
def resolve_schedule_card_answer(request, schedule_id: int, user_word_id: int):
    try:
        schedule = get_user_schedule(request.auth, schedule_id)
    except ScheduleError as error:
        raise_service_error(error)

    cards = list_schedule_cards(schedule, user_word_id=user_word_id)
    if not cards:
        raise HttpError(404, "card_not_found")
    card = cards[0]
    if schedule.exercise_kind != schedule.ExerciseKind.TRANSLATION or card["answer"] is not None:
        return 200, card

    try:
        word = Word.objects.get(pk=card["word_id"])
        ensure_main_translation(word, request.auth.current_using_language)
    except TranslationUnavailableError as error:
        raise HttpError(422, error.status) from error
    except Exception as error:
        logger.exception("Could not generate translation for word %s", card["word_id"])
        raise HttpError(502, "translation_unavailable") from error

    refreshed = list_schedule_cards(schedule, user_word_id=user_word_id)
    if not refreshed:
        raise HttpError(404, "card_not_found")
    return 200, refreshed[0]


@schedules_router.patch(
    "/{schedule_id}",
    response={
        200: StudyScheduleOut,
        400: ErrorOut,
        401: ErrorOut,
        404: ErrorOut,
        422: ErrorOut,
    },
)
def update_schedule(request, schedule_id: int, data: StudyScheduleUpdateIn):
    try:
        schedule = update_study_schedule(
            request.auth,
            schedule_id,
            data.model_dump(exclude_unset=True),
        )
    except ScheduleError as error:
        raise_service_error(error)

    return 200, serialize_schedule(schedule)


@schedules_router.delete(
    "/{schedule_id}",
    response={
        204: None,
        401: ErrorOut,
        404: ErrorOut,
        409: ErrorOut,
    },
)
def delete_schedule(request, schedule_id: int):
    try:
        delete_study_schedule(request.auth, schedule_id)
    except ScheduleError as error:
        raise_service_error(error)

    return 204, None


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
    try:
        run = create_schedule_run_for_user(request.auth, schedule_id)
    except ScheduleError as error:
        raise_service_error(error)

    return 201, serialize_schedule_run(run)
