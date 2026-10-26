from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from translations.models import BaseTranslation, UserTag, UserWord


def _get_user_word(user, user_word_id: int) -> UserWord:
    return get_object_or_404(
        UserWord.objects.prefetch_related("tags"),
        pk=user_word_id,
        user=user,
    )


def _get_user_tags(user, tag_ids: list[int]) -> list[UserTag]:
    tags = list(UserTag.objects.filter(user=user, pk__in=tag_ids))
    if len(tags) != len(set(tag_ids)):
        raise HttpError(400, "invalid_tag_ids")
    return tags


def _validate_selected_translation(selected_translation_id: int | None, word_id: int) -> None:
    if (
        selected_translation_id is not None
        and not BaseTranslation.objects.filter(pk=selected_translation_id, word_id=word_id).exists()
    ):
        raise HttpError(400, "selected_translation_does_not_belong_to_word")
