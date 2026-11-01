from typing import Literal

from authentication.auth import BotAuth, GlobalAuth
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from words.models import UserWord, Word, WordInflection
from words.schemas import (
    UserWordIn,
    UserWordOut,
    UserWordUpdate,
    WordIn,
    WordInflectionIn,
    WordInflectionOut,
    WordInflectionUpdate,
    WordOut,
    WordPageOut,
)
from words.services import (
    _get_readable_inflection_word,
    _get_user_tags,
    _get_user_word,
    _get_writable_inflection_word,
    _validate_inflection_type,
    _validate_selected_translation,
)

words_router = Router()
user_words_router = Router(auth=[GlobalAuth(), BotAuth()])
_MISSING = object()
_inflection_auth = [GlobalAuth(), BotAuth()]
_WORD_PAGE_SIZE = 100


@words_router.post("", response=WordOut)
def add_word(request, word: WordIn):
    word_obj, _created = Word.objects.get_or_create(**word.model_dump())
    return word_obj


@words_router.get("/{int:word_id}", response=WordOut)
def get_word(request, word_id: int):
    return get_object_or_404(Word, pk=word_id)


@words_router.get("/pages/{sort}/{page}", response=WordPageOut)
def get_word_page(request, sort: Literal["id", "popular"], page: int):
    if page < 1:
        raise HttpError(422, "page_must_be_positive")

    words = Word.objects.all()
    if sort == "popular":
        words = words.annotate(popularity=Count("user_links")).order_by("-popularity", "id")
    else:
        words = words.order_by("id")

    offset = (page - 1) * _WORD_PAGE_SIZE
    items = list(words[offset : offset + _WORD_PAGE_SIZE + 1])
    return {
        "page": page,
        "sort": sort,
        "page_size": _WORD_PAGE_SIZE,
        "words": items[:_WORD_PAGE_SIZE],
        "has_next": len(items) > _WORD_PAGE_SIZE,
    }


@words_router.get("/{int:word_id}/inflections", response=list[WordInflectionOut], auth=_inflection_auth)
def list_word_inflections(request, word_id: int):
    word = _get_readable_inflection_word(request.auth, word_id)
    return WordInflection.objects.filter(word=word).order_by("type")


@words_router.post("/{int:word_id}/inflections", response={201: WordInflectionOut}, auth=_inflection_auth)
def create_word_inflection(request, word_id: int, data: WordInflectionIn):
    word = _get_writable_inflection_word(request.auth, word_id)
    _validate_inflection_type(word, data.type)
    try:
        with transaction.atomic():
            inflection = WordInflection.objects.create(word=word, **data.model_dump())
    except IntegrityError as error:
        raise HttpError(409, "inflection_type_exists") from error
    return 201, inflection


@words_router.get("/{int:word_id}/inflections/{int:inflection_id}", response=WordInflectionOut, auth=_inflection_auth)
def get_word_inflection(request, word_id: int, inflection_id: int):
    word = _get_readable_inflection_word(request.auth, word_id)
    return get_object_or_404(WordInflection, pk=inflection_id, word=word)


@words_router.patch("/{int:word_id}/inflections/{int:inflection_id}", response=WordInflectionOut, auth=_inflection_auth)
def update_word_inflection(request, word_id: int, inflection_id: int, data: WordInflectionUpdate):
    word = _get_writable_inflection_word(request.auth, word_id)
    payload = data.model_dump(exclude_unset=True)
    if any(value is None for value in payload.values()):
        raise HttpError(422, "inflection_fields_cannot_be_null")
    if "type" in payload:
        _validate_inflection_type(word, payload["type"])

    try:
        with transaction.atomic():
            inflection = get_object_or_404(WordInflection.objects.select_for_update(), pk=inflection_id, word=word)
            for field, value in payload.items():
                setattr(inflection, field, value)
            if payload:
                inflection.save(update_fields=[*payload, "updated_at"])
    except IntegrityError as error:
        raise HttpError(409, "inflection_type_exists") from error
    return inflection


@words_router.delete("/{int:word_id}/inflections/{int:inflection_id}", response={204: None}, auth=_inflection_auth)
def delete_word_inflection(request, word_id: int, inflection_id: int):
    word = _get_writable_inflection_word(request.auth, word_id)
    inflection = get_object_or_404(WordInflection, pk=inflection_id, word=word)
    inflection.delete()
    return 204, None


@user_words_router.post("", response=UserWordOut)
def add_user_word(request, data: UserWordIn):
    payload = data.model_dump()
    word_id = payload.pop("word")
    tag_ids = payload.pop("tags")
    selected_translation_id = payload.pop("selected_translation")

    word = get_object_or_404(Word, pk=word_id)
    tags = _get_user_tags(request.auth, tag_ids)
    _validate_selected_translation(selected_translation_id, word.pk)
    payload["selected_translation_id"] = selected_translation_id

    with transaction.atomic():
        user_word, created = UserWord.objects.get_or_create(
            user=request.auth,
            word=word,
            defaults=payload,
        )
        if created:
            user_word.tags.set(tags)

    return user_word


@user_words_router.get("", response=list[UserWordOut])
def get_user_words(request):
    return UserWord.objects.filter(user=request.auth).prefetch_related("tags")


@user_words_router.get("/{user_word_id}", response=UserWordOut)
def get_user_word(request, user_word_id: int):
    return _get_user_word(request.auth, user_word_id)


@user_words_router.patch("/{user_word_id}", response=UserWordOut)
def update_user_word(request, user_word_id: int, data: UserWordUpdate):
    payload = data.model_dump(exclude_unset=True)
    tag_ids = payload.pop("tags", _MISSING)

    if "status" in payload and payload["status"] is None:
        raise HttpError(422, "status_cannot_be_null")

    user_word = _get_user_word(request.auth, user_word_id)

    if "selected_translation" in payload:
        selected_translation_id = payload.pop("selected_translation")
        _validate_selected_translation(selected_translation_id, user_word.word_id)
        payload["selected_translation_id"] = selected_translation_id

    tags = _get_user_tags(request.auth, tag_ids or []) if tag_ids is not _MISSING else None

    with transaction.atomic():
        for field, value in payload.items():
            setattr(user_word, field, value)

        if payload or tags is not None:
            user_word.save()

        if tags is not None:
            user_word.tags.set(tags)

    return user_word


@user_words_router.delete("/{user_word_id}", response={204: None})
def delete_user_word(request, user_word_id: int):
    user_word = _get_user_word(request.auth, user_word_id)
    user_word.delete()
    return 204, None


words_router.add_router("/me", user_words_router)
