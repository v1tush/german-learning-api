from typing import Literal

from authentication.auth import BotAuth, GlobalAuth
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from words.models import UserWord, UserWordTranslation, Word, WordInflection
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
    replace_translation_selection,
    serialize_user_word,
)

words_router = Router()
user_words_router = Router(auth=[GlobalAuth(), BotAuth()])
_MISSING = object()
_inflection_auth = [GlobalAuth(), BotAuth()]
_WORD_PAGE_SIZE = 100
_TRANSLATION_CONSTRAINTS = {
    "user_word_translation_one_source",
    "unique_user_word_base_translation",
    "unique_user_word_custom_per_language",
}


def _raise_translation_integrity_error(error: IntegrityError) -> None:
    constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
    if constraint in _TRANSLATION_CONSTRAINTS:
        raise HttpError(409, "translation_selection_conflict") from error
    raise error


def _current_translation_prefetch(target_language: str) -> Prefetch:
    return Prefetch(
        "translations",
        queryset=UserWordTranslation.objects.filter(target_language=target_language).select_related("base_translation"),
        to_attr="current_translations",
    )


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
    payload.pop("translation_selection")

    word = get_object_or_404(Word, pk=word_id)
    tags = _get_user_tags(request.auth, tag_ids)

    try:
        with transaction.atomic():
            user_word, created = UserWord.objects.get_or_create(
                user=request.auth,
                word=word,
                defaults=payload,
            )
            if created:
                user_word.tags.set(tags)
                if data.translation_selection is not None:
                    replace_translation_selection(
                        user_word, request.auth.current_using_language, data.translation_selection
                    )
    except IntegrityError as error:
        _raise_translation_integrity_error(error)

    return serialize_user_word(user_word, request.auth.current_using_language)


@user_words_router.get("", response=list[UserWordOut])
def get_user_words(request):
    words = UserWord.objects.filter(user=request.auth).prefetch_related(
        "tags", _current_translation_prefetch(request.auth.current_using_language)
    )
    return [serialize_user_word(word, request.auth.current_using_language) for word in words]


@user_words_router.get("/{user_word_id}", response=UserWordOut)
def get_user_word(request, user_word_id: int):
    return serialize_user_word(_get_user_word(request.auth, user_word_id), request.auth.current_using_language)


@user_words_router.patch("/{user_word_id}", response=UserWordOut)
def update_user_word(request, user_word_id: int, data: UserWordUpdate):
    payload = data.model_dump(exclude_unset=True)
    tag_ids = payload.pop("tags", _MISSING)
    selection = payload.pop("translation_selection", _MISSING)

    if "status" in payload and payload["status"] is None:
        raise HttpError(422, "status_cannot_be_null")
    if selection is None:
        raise HttpError(422, "translation_selection_cannot_be_null")

    tags = _get_user_tags(request.auth, tag_ids or []) if tag_ids is not _MISSING else None

    try:
        with transaction.atomic():
            user_word = get_object_or_404(UserWord.objects.select_for_update(), pk=user_word_id, user=request.auth)
            for field, value in payload.items():
                setattr(user_word, field, value)
            if selection is not _MISSING:
                replace_translation_selection(
                    user_word, request.auth.current_using_language, data.translation_selection
                )
            if payload or tags is not None or selection is not _MISSING:
                user_word.save()
            if tags is not None:
                user_word.tags.set(tags)
    except IntegrityError as error:
        _raise_translation_integrity_error(error)

    return serialize_user_word(user_word, request.auth.current_using_language)


@user_words_router.delete("/{user_word_id}", response={204: None})
def delete_user_word(request, user_word_id: int):
    user_word = _get_user_word(request.auth, user_word_id)
    user_word.delete()
    return 204, None


words_router.add_router("/me", user_words_router)
