from authentication.auth import GlobalAuth
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError
from translations.models import UserWord

from words.models import Word
from words.schemas import UserWordIn, UserWordOut, UserWordUpdate, WordIn, WordOut
from words.services import _get_user_tags, _get_user_word, _validate_selected_translation

words_router = Router()
user_words_router = Router(auth=GlobalAuth())
_MISSING = object()


@words_router.post("", response=WordOut)
def add_word(request, word: WordIn):
    word_obj, _created = Word.objects.get_or_create(**word.model_dump())
    return word_obj


@words_router.get("/{word_id}", response=WordOut)
def get_word(request, word_id: int):
    return get_object_or_404(Word, pk=word_id)


@words_router.get("", response=list[WordOut])
def get_words(request):
    return Word.objects.all()


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
