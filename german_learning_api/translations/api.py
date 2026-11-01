from authentication.auth import BotAuth, GlobalAuth
from ninja import Router

from translations.schemas import TranslationResponse, TranslationsListResponse
from translations.services import (
    TranslationUnavailableError,
    ensure_main_translation,
    get_word_translations,
    serialize_translations,
)

translations_router = Router(auth=[GlobalAuth(), BotAuth()])


@translations_router.get(
    "/words/{word_id}/translations",
    response=TranslationsListResponse,
)
def get_translations(request, word_id: int):
    target_language = request.auth.current_using_language
    word, translations = get_word_translations(
        word_id,
        target_language,
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
    target_language = request.auth.current_using_language
    word, translations = get_word_translations(word_id, target_language)

    if translations.exists():
        return {
            "word": word.word,
            "part_of_speech": word.part_of_speech,
            "status": "success",
            "translations": serialize_translations(translations),
        }

    try:
        ensure_main_translation(word, target_language)
    except TranslationUnavailableError as error:
        return {
            "word": word.word,
            "part_of_speech": word.part_of_speech,
            "status": error.status,
            "translations": [],
        }
    return {
        "word": word.word,
        "part_of_speech": word.part_of_speech,
        "status": "success",
        "translations": serialize_translations(translations),
    }
