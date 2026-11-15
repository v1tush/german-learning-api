import unicodedata

from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from tags.models import UserTag
from translations.models import BaseTranslation

from words.choices import InflectionTypeChoices, LanguageChoices, PartOfSpeechChoices
from words.models import UserWord, UserWordTranslation, Word
from words.schemas import UserWordTranslationSelectionIn

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


def _translation_key(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def replace_translation_selection(
    user_word: UserWord, target_language: str, selection: UserWordTranslationSelectionIn
) -> None:
    """Replace one language's selection while the caller holds the UserWord row lock."""
    base_ids = selection.base_translation_ids
    primary_ids = selection.primary_base_translation_ids
    custom = unicodedata.normalize("NFC", " ".join((selection.custom_translation or "").split())) or None

    if len(base_ids) > 5:
        raise HttpError(422, "too_many_base_translations")
    if len(base_ids) != len(set(base_ids)):
        raise HttpError(422, "duplicate_base_translations")
    if len(primary_ids) != len(set(primary_ids)) or not set(primary_ids).issubset(base_ids):
        raise HttpError(422, "invalid_primary_translations")
    if selection.custom_is_card_primary and custom is None:
        raise HttpError(422, "custom_primary_requires_translation")

    primary_count = len(primary_ids) + int(selection.custom_is_card_primary)
    if primary_count > 2 or (primary_count == 0 and (base_ids or custom)):
        raise HttpError(422, "primary_translation_count_must_be_one_or_two")

    base_translations = {
        item.pk: item
        for item in BaseTranslation.objects.filter(
            pk__in=base_ids,
            word_id=user_word.word_id,
            target_language=target_language,
        )
    }
    if len(base_translations) != len(base_ids):
        raise HttpError(422, "invalid_base_translations_for_word_or_language")
    if any(not item.translation.strip() for item in base_translations.values()):
        raise HttpError(422, "empty_base_translation")
    if custom and _translation_key(custom) in {
        _translation_key(item.translation) for item in base_translations.values()
    }:
        raise HttpError(422, "custom_translation_duplicates_base")

    user_word.translations.filter(target_language=target_language).delete()
    rows = [
        UserWordTranslation(
            user_word=user_word,
            target_language=target_language,
            base_translation=base_translations[base_id],
            is_card_primary=base_id in primary_ids,
        )
        for base_id in base_ids
    ]
    if custom:
        rows.append(
            UserWordTranslation(
                user_word=user_word,
                target_language=target_language,
                custom_translation=custom,
                is_card_primary=selection.custom_is_card_primary,
            )
        )
    UserWordTranslation.objects.bulk_create(rows)


def serialize_user_word(user_word: UserWord, target_language: str) -> dict:
    rows = getattr(user_word, "current_translations", None)
    if rows is None:
        rows = list(
            UserWordTranslation.objects.filter(user_word=user_word, target_language=target_language)
            .select_related("base_translation")
            .order_by("id")
        )
    base_translations = []
    custom_translation = None
    custom_is_card_primary = False
    for row in rows:
        if row.base_translation_id is None:
            custom_translation = row.custom_translation
            custom_is_card_primary = row.is_card_primary
        else:
            base_translations.append(
                {
                    "id": row.base_translation_id,
                    "value": row.base_translation.translation,
                    "is_card_primary": row.is_card_primary,
                }
            )

    return {
        "id": user_word.pk,
        "word_id": user_word.word_id,
        "user_hint": user_word.user_hint,
        "tags": sorted(tag.pk for tag in user_word.tags.all()),
        "status": user_word.status,
        "translation_selection": {
            "target_language": target_language,
            "base_translations": base_translations,
            "custom_translation": custom_translation,
            "custom_is_card_primary": custom_is_card_primary,
        },
        "created_at": user_word.created_at,
        "updated_at": user_word.updated_at,
    }


def get_custom_translation(user_word: UserWord, target_language: str) -> str | None:
    for row in user_word.translations.all():
        if row.target_language == target_language and row.base_translation_id is None:
            return row.custom_translation
    return None
