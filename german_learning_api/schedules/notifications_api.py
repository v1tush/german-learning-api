from datetime import datetime

from authentication.auth import GlobalAuth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from schedules.models import SiteNotification
from schedules.schemas import ErrorOut


class SiteNotificationOut(Schema):
    id: int
    run_id: int
    schedule_id: int
    dataset_id: int | None
    scheduled_for: datetime
    exercise_kind: str
    inflection_type: str | None
    created_at: datetime
    read_at: datetime | None


notifications_router = Router(auth=GlobalAuth())


def serialize_notification(notification: SiteNotification) -> dict:
    run = notification.run
    return {
        "id": notification.pk,
        "run_id": run.pk,
        "schedule_id": run.schedule_id,
        "dataset_id": run.schedule.dataset_id,
        "scheduled_for": run.scheduled_for,
        "exercise_kind": run.exercise_kind,
        "inflection_type": run.inflection_type,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


@notifications_router.get("/", response=list[SiteNotificationOut])
def list_notifications(request, unread_only: bool = True):
    notifications = SiteNotification.objects.filter(run__schedule__user=request.auth).select_related("run__schedule")
    if unread_only:
        notifications = notifications.filter(read_at__isnull=True)
    return [serialize_notification(notification) for notification in notifications.order_by("-created_at", "-pk")]


@notifications_router.post("/{notification_id}/read", response={200: SiteNotificationOut, 404: ErrorOut})
def read_notification(request, notification_id: int):
    notification = get_object_or_404(
        SiteNotification.objects.select_related("run__schedule").filter(run__schedule__user=request.auth),
        pk=notification_id,
    )
    if notification.read_at is None:
        now = timezone.now()
        SiteNotification.objects.filter(pk=notification.pk, read_at__isnull=True).update(read_at=now, updated_at=now)
        notification.refresh_from_db(fields=["read_at", "updated_at"])
    return serialize_notification(notification)
