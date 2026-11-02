import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja.errors import HttpError

from users.models import TelegramLinkRequest

User = get_user_model()
TELEGRAM_LINK_LIFETIME = timedelta(minutes=10)
MAX_TELEGRAM_ID = 2**63 - 1


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_telegram_link(user) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + TELEGRAM_LINK_LIFETIME

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        if not user.is_active:
            raise HttpError(403, "account_disabled")
        if user.telegram_id is not None:
            raise HttpError(409, "telegram_already_linked")
        TelegramLinkRequest.objects.update_or_create(
            user=user,
            defaults={"token_hash": _token_hash(token), "expires_at": expires_at},
        )

    return {"token": token, "expires_at": expires_at}


def parse_telegram_id(raw_id: str | None) -> int:
    if raw_id is None:
        raise HttpError(400, "missing_telegram_id")
    if not raw_id.isascii() or not raw_id.isdecimal():
        raise HttpError(400, "invalid_telegram_id")
    telegram_id = int(raw_id)
    if not 0 < telegram_id <= MAX_TELEGRAM_ID:
        raise HttpError(400, "invalid_telegram_id")
    return telegram_id


def confirm_telegram_link(token: str, telegram_id: int) -> dict:
    token_hash = _token_hash(token)
    user_id = TelegramLinkRequest.objects.filter(token_hash=token_hash).values_list("user_id", flat=True).first()
    if user_id is None:
        raise HttpError(400, "invalid_or_expired_telegram_link_token")

    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=user_id).first()
            link = (
                TelegramLinkRequest.objects.select_for_update().filter(user_id=user_id, token_hash=token_hash).first()
            )
            if user is None or link is None or link.expires_at <= timezone.now():
                raise HttpError(400, "invalid_or_expired_telegram_link_token")
            if not user.is_active:
                raise HttpError(403, "account_disabled")
            if user.telegram_id is not None:
                raise HttpError(409, "telegram_already_linked")
            if User.objects.filter(telegram_id=telegram_id).exists():
                raise HttpError(409, "telegram_id_already_linked")

            user.telegram_id = telegram_id
            user.save(update_fields=["telegram_id"])
            link.delete()
    except IntegrityError as error:
        raise HttpError(409, "telegram_id_already_linked") from error

    return {"user_id": user.pk, "telegram_id": user.telegram_id}
