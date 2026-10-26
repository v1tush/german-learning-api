import json

from django.shortcuts import get_object_or_404
from words.models import Word

from translations.integrations.yandex_ai import call_api, word_to_dict
from translations.schemas import TranslationResponse


def get_translation(word: Word, target_language: str) -> TranslationResponse:
    word_data = word_to_dict(word)
    word_data["target_language"] = target_language
    response = call_api(word_data)

    if response.status != "completed":
        raise ValueError("Response is incomplete")

    message = response.output_text

    if not message:
        raise ValueError("No message from the model")

    data = json.loads(message)

    result = TranslationResponse.model_validate(data)

    return result


def get_word_translations(word_id: int, target_language: str):
    word = get_object_or_404(Word, pk=word_id)
    translations = word.base_translations.filter(target_language=target_language)
    return word, translations


def serialize_translations(translations):
    return [
        {
            "value": translation.translation,
            "is_main": translation.is_main,
        }
        for translation in translations
    ]
