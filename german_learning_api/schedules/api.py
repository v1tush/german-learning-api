from authentication.auth import GlobalAuth
from ninja import Router
from ninja.errors import HttpError

from schedules.errors import ScheduleError
from schedules.schemas import (
    ErrorOut,
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

schedules_router = Router(auth=GlobalAuth())


def raise_service_error(error: ScheduleError) -> None:
    raise HttpError(error.status_code, error.code) from error


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
            items_per_delivery=data.items_per_delivery,
            timezone_name=data.timezone,
            interval_minutes=data.interval_minutes,
            fixed_times=data.fixed_times,
            tag_ids=data.tags,
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
