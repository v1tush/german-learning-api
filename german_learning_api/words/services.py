from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from tags.models import UserTag
from translations.models import BaseTranslation

from words.choices import InflectionTypeChoices, LanguageChoices, PartOfSpeechChoices
from words.models import UserWord, Word

_INFLECTION_WORD_TYPES = {
    InflectionTypeChoices.DE_PRATERITUM: (LanguageChoices.GERMAN, PartOfSpeechChoices.VERB),
    InflectionTypeChoices.DE_PARTIZIP_2: (LanguageChoices.GERMAN, PartOfSpeechChoices.VERB),
    InflectionTypeChoices.DE_PLURAL: (LanguageChoices.GERMAN, PartOfSpeechChoices.NOUN),
    InflectionTypeChoices.EN_PAST_SIMPLE: (LanguageChoices.ENGLISH, PartOfSpeechChoices.VERB),
    InflectionTypeChoices.EN_PAST_PARTICIPLE: (LanguageChoices.ENGLISH, PartOfSpeechChoices.VERB),
    InflectionTypeChoices.EN_GERUND: (LanguageChoices.ENGLISH, PartOfSpeechChoices.VERB),
}


def _get_owned_word(user, word_id: int) -> Word:
    return get_object_or_404(Word.objects.filter(user_links__user=user), pk=word_id)


def _get_readable_inflection_word(user, word_id: int) -> Word:
    if user.is_active and user.is_staff:
        return get_object_or_404(Word, pk=word_id)
    return _get_owned_word(user, word_id)


def _get_writable_inflection_word(user, word_id: int) -> Word:
    if not user.is_active or not user.is_staff:
        raise HttpError(403, "staff_only")
    return get_object_or_404(Word, pk=word_id)


def _validate_inflection_type(word: Word, inflection_type: InflectionTypeChoices) -> None:
    if (word.language, word.part_of_speech) != _INFLECTION_WORD_TYPES.get(inflection_type):
        raise HttpError(422, "inflection_type_does_not_match_word")


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
