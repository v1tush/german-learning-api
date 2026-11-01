import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from words.models import Word

from translations.integrations.yandex_ai import call_api, word_to_dict
from translations.models import BaseTranslation
from translations.schemas import TranslationResponse


class TranslationUnavailableError(Exception):
    def __init__(self, status: str = "not_found"):
        self.status = status
        super().__init__(status)


def get_translation(word: Word, target_language: str, max_attempts: int = 2) -> TranslationResponse:
    word_data = word_to_dict(word)
    word_data["target_language"] = target_language
    for attempt in range(max_attempts):
        try:
            response = call_api(word_data)
            if response.status != "completed":
                raise ValueError("Response is incomplete")

            message = response.output_text

            if not message:
                raise ValueError("No message from the model")

            data = json.loads(message)
            return TranslationResponse.model_validate(data)
        except Exception:
            if attempt == max_attempts - 1:
                raise


def ensure_main_translation(word: Word, target_language: str) -> BaseTranslation:
    """Generate and save translations only when the word has no main one."""
    translations = BaseTranslation.objects.filter(word=word, target_language=target_language)
    existing_main = translations.filter(is_main=True).first()
    if existing_main is not None and existing_main.translation.strip():
        return existing_main

    result = get_translation(word, target_language)
    if result.status != "success":
        raise TranslationUnavailableError(result.status)

    suggestions = []
    seen = set()
    for suggestion in result.translations:
        value = suggestion.value.strip()
        if value and value not in seen:
            suggestions.append((value, suggestion.is_main))
            seen.add(value)
    if not suggestions:
        raise TranslationUnavailableError()

    main_value = next((value for value, is_main in suggestions if is_main), suggestions[0][0])
    with transaction.atomic():
        Word.objects.select_for_update().get(pk=word.pk)
        translations = BaseTranslation.objects.filter(word=word, target_language=target_language)
        existing_main = translations.filter(is_main=True).first()
        if existing_main is not None and existing_main.translation.strip():
            return existing_main
        if existing_main is not None:
            existing_main.is_main = False
            existing_main.save(update_fields=["is_main", "updated_at"])

        existing_by_value = {item.translation: item for item in translations}
        for value, _ in suggestions:
            item = existing_by_value.get(value)
            if item is None:
                item = BaseTranslation.objects.create(
                    word=word,
                    target_language=target_language,
                    translation=value,
                    is_main=value == main_value,
                )
            elif value == main_value:
                item.is_main = True
                item.save(update_fields=["is_main", "updated_at"])
            existing_by_value[value] = item
        return existing_by_value[main_value]


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
