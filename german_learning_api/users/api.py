from uuid import uuid4

from authentication.auth import BotAuth, BotServiceAuth, GlobalAuth
from core.exceptions import TooManyPixelsError, WrongFileSizeError, WrongImageTypeError
from core.validators import validate_avatar
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from ninja import File, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile
from PIL import UnidentifiedImageError

from users.schemas import (
    TelegramLinkConfirmIn,
    TelegramLinkConfirmOut,
    TelegramLinkIssueOut,
    TelegramRegisterIn,
    UserMeOut,
    UserMeUpdateIn,
)
from users.services import confirm_telegram_link, issue_telegram_link, parse_telegram_id, register_telegram_user

User = get_user_model()

users_router = Router(auth=[GlobalAuth(), BotAuth()])
me_router = Router()

users_router.add_router("/me/", me_router)


@me_router.get("/", response=UserMeOut)
def me(request):
    return request.auth


@me_router.patch("/", response=UserMeOut)
def update_me(request, data: UserMeUpdateIn):
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return request.auth

    if "username" in changes:
        if changes["username"] is None or not changes["username"].strip():
            raise HttpError(422, "username_cannot_be_empty")
        changes["username"] = changes["username"].strip()
    for field in ("current_using_language", "current_learning_language"):
        if field in changes and changes[field] is None:
            raise HttpError(422, f"{field}_cannot_be_empty")
    if "email" in changes:
        email = changes["email"]
        if email:
            email = email.strip()
            try:
                validate_email(email)
            except ValidationError as error:
                raise HttpError(422, "invalid_email") from error
        changes["email"] = email or None

    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.auth.pk)
            if not user.is_active:
                raise HttpError(403, "account_disabled")
            for field, value in changes.items():
                setattr(user, field, value)
            user.save(update_fields=list(changes))
    except IntegrityError as error:
        if (
            "username" in changes
            and User.objects.filter(username=changes["username"]).exclude(pk=request.auth.pk).exists()
        ):
            raise HttpError(409, "username_already_exists") from error
        if (
            "email" in changes
            and changes["email"]
            and User.objects.filter(email=changes["email"]).exclude(pk=request.auth.pk).exists()
        ):
            raise HttpError(409, "email_already_exists") from error
        raise
    return user


@me_router.post("/avatar", response=UserMeOut)
def upload_avatar(request, avatar: File[UploadedFile]):
    if not request.auth.is_active:
        raise HttpError(403, "account_disabled")
    try:
        processed = validate_avatar(avatar)
    except (WrongImageTypeError, WrongFileSizeError, TooManyPixelsError) as error:
        raise HttpError(error.code, str(error)) from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HttpError(422, "invalid_avatar_image") from error

    processed.name = f"{uuid4().hex}.{processed.name.rsplit('.', 1)[-1]}"
    user = request.auth
    user.avatar.save(processed.name, processed, save=True)
    return user


@me_router.delete("/avatar", response=UserMeOut)
def delete_avatar(request):
    user = request.auth
    if not user.is_active:
        raise HttpError(403, "account_disabled")
    if user.avatar:
        user.avatar.delete(save=True)
    return user


@me_router.post("/telegram-link", response={201: TelegramLinkIssueOut}, auth=GlobalAuth())
def create_telegram_link(request, response: HttpResponse):
    response["Cache-Control"] = "no-store"
    return 201, issue_telegram_link(request.auth)


@users_router.post("/telegram-link/confirm", response=TelegramLinkConfirmOut, auth=BotServiceAuth())
def confirm_telegram_link_from_bot(request, data: TelegramLinkConfirmIn):
    telegram_id = parse_telegram_id(request.headers.get("X-Telegram-ID"))
    return confirm_telegram_link(data.token, telegram_id)


@users_router.post("/telegram-register", response={201: UserMeOut}, auth=BotServiceAuth())
def register_user_from_bot(request, data: TelegramRegisterIn):
    telegram_id = parse_telegram_id(request.headers.get("X-Telegram-ID"))
    return 201, register_telegram_user(
        telegram_id,
        username=data.username,
        current_using_language=data.current_using_language,
        current_learning_language=data.current_learning_language,
    )
