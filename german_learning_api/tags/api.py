from django.db import IntegrityError, transaction
from ninja import Router
from ninja.errors import HttpError

from authentication.auth import GlobalAuth, BotAuth
from tags.models import UserTag
from tags.schemas import (
    ErrorOut,
    TagCreate,
    TagDetailOut,
    TagOut,
    TagWordOut,
    TagWordsAddedOut,
    TagWordsIn,
    TagWordsRemovedOut,
)
from tags.utils import get_user_tag, serialize_user_word, get_user_words, validate_user_word_ids
from words.models import UserWord


tags_router = Router(auth=[GlobalAuth(), BotAuth()])

@tags_router.post(
    "/",
    response={
        201: TagOut,
        400: ErrorOut,
        401: ErrorOut,
        409: ErrorOut,
    },
)
def create_tag(request, payload: TagCreate):
    name = payload.name.strip()

    if not name:
        raise HttpError(400, "tag_name_cannot_be_empty")

    if len(name) > 50:
        raise HttpError(400, "tag_name_too_long")

    try:
        with transaction.atomic():
            tag = UserTag.objects.create(
                user=request.auth,
                name=name,
            )
    except IntegrityError as exc:
        if UserTag.objects.filter(
            user=request.auth,
            name=name,
        ).exists():
            raise HttpError(409, "tag_already_exists") from exc

        raise

    return 201, {
        "id": tag.id,
        "name": tag.name,
    }


@tags_router.get(
    "/",
    response={
        200: list[TagOut],
        401: ErrorOut,
    },
)
def get_tags(request):
    tags = UserTag.objects.filter(
        user=request.auth,
    ).order_by("name")

    return 200, [
        {
            "id": tag.id,
            "name": tag.name,
        }
        for tag in tags
    ]


@tags_router.get(
    "/{tag_id}",
    response={
        200: TagDetailOut,
        401: ErrorOut,
        404: ErrorOut,
    },
)
def get_tag(request, tag_id: int):
    tag = get_user_tag(request, tag_id)

    return 200, {
        "id": tag.id,
        "name": tag.name,
        "weight": tag.user_words.count(),
    }


@tags_router.delete(
    "/{tag_id}",
    response={
        204: None,
        401: ErrorOut,
        404: ErrorOut,
    },
)
def delete_tag(request, tag_id: int):
    tag = get_user_tag(request, tag_id)
    tag.delete()

    return 204, None


@tags_router.get(
    "/{tag_id}/words",
    response={
        200: list[TagWordOut],
        401: ErrorOut,
        404: ErrorOut,
    },
)
def get_tag_words(request, tag_id: int):
    tag = get_user_tag(request, tag_id)

    user_words = (
        UserWord.objects.filter(
            user=request.auth,
            tags=tag,
        )
        .select_related("word")
        .order_by("id")
    )

    return 200, [
        serialize_user_word(user_word)
        for user_word in user_words
    ]


@tags_router.post(
    "/{tag_id}/words",
    response={
        200: TagWordsAddedOut,
        400: ErrorOut,
        401: ErrorOut,
        404: ErrorOut,
    },
)
def add_words_to_tag(
    request,
    tag_id: int,
    payload: TagWordsIn,
):
    tag = get_user_tag(request, tag_id)

    user_word_ids = set(payload.user_word_ids)
    validate_user_word_ids(user_word_ids)

    user_words = get_user_words(request, user_word_ids)

    existing_ids = set(
        tag.user_words.filter(
            id__in=user_word_ids,
        ).values_list("id", flat=True)
    )

    tag.user_words.add(*user_words)

    return 200, {
        "added": len(user_word_ids - existing_ids),
        "already_in_tag": len(existing_ids),
    }


@tags_router.delete(
    "/{tag_id}/words",
    response={
        200: TagWordsRemovedOut,
        400: ErrorOut,
        401: ErrorOut,
        404: ErrorOut,
    },
)
def remove_words_from_tag(
    request,
    tag_id: int,
    payload: TagWordsIn,
):
    tag = get_user_tag(request, tag_id)

    user_word_ids = set(payload.user_word_ids)
    validate_user_word_ids(user_word_ids)

    user_words = get_user_words(request, user_word_ids)

    existing_ids = set(
        tag.user_words.filter(
            id__in=user_word_ids,
        ).values_list("id", flat=True)
    )

    tag.user_words.remove(*user_words)

    return 200, {
        "removed": len(existing_ids),
        "not_in_tag": len(user_word_ids - existing_ids),
    }

