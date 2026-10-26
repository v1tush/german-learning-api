from django.db import transaction
from ninja import Router

from translations.models import BaseTranslation
from translations.schemas import TranslationResponse, TranslationsListResponse
from translations.services import get_translation, get_word_translations, serialize_translations

translations_router = Router()


@translations_router.get(
    "/words/{word_id}/translations",
    response=TranslationsListResponse,
)
def get_translations(request, word_id: int):
    word, translations = get_word_translations(
        word_id,
        request.user.current_learning_language,
    )

    return {
        "word": word.word,
        "part_of_speech": word.part_of_speech,
        "translations": serialize_translations(translations),
    }


@translations_router.post(
    "/words/{word_id}/translation-suggestions",
    response=TranslationResponse,
)
def get_translation_suggestions(request, word_id: int):
    target_language = request.user.current_learning_language
    word, translations = get_word_translations(word_id, target_language)

    if translations.exists():
        return {
            "word": word.word,
            "part_of_speech": word.part_of_speech,
            "status": "success",
            "translations": serialize_translations(translations),
        }

    result = get_translation(word, target_language)

    if result.status != "success":
        return result

    with transaction.atomic():
        BaseTranslation.objects.bulk_create(
            [
                BaseTranslation(
                    word=word,
                    target_language=target_language,
                    translation=translation.value,
                    is_main=translation.is_main,
                )
                for translation in result.translations
            ]
        )

    return result
