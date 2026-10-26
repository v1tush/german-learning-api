import openai
from django.conf import settings
from words.models import Word

client = openai.OpenAI(
    api_key=settings.YANDEX_CLOUD_API_KEY,
    base_url=settings.YANDEX_CLOUD_BASE_URL,
    project=settings.YANDEX_CLOUD_FOLDER,
    timeout=10.0,
    max_retries=1,
)

with open("word_translation_prompt.txt", "r", encoding="utf-8") as file:
    BASE_PROMPT = file.read()


def word_to_dict(word: Word) -> dict:
    return {
        "word": word.word,
        "language": word.language,
        "part_of_speech": word.part_of_speech,
    }


def call_api(word_data):
    return client.responses.create(
        model=f"gpt://{settings.YANDEX_CLOUD_FOLDER}/{settings.YANDEX_CLOUD_MODEL}",
        instructions=BASE_PROMPT,
        input=word_data,
        temperature=0.2,
        max_output_tokens=500,
        text={  # type: ignore
            "format": {
                "type": "json_schema",
                "name": "word_translation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string"},
                        "part_of_speech": {"type": "string", "enum": ["noun", "verb", "adj", "adv"]},
                        "status": {"type": "string", "enum": ["success", "not_found", "invalid_input"]},
                        "translations": {
                            "type": "array",
                            "maxItems": 5,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string", "minLength": 1},
                                    "is_main": {"type": "boolean"},
                                },
                                "required": ["value", "is_main"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["word", "part_of_speech", "status", "translations"],
                    "additionalProperties": False,
                },
            }
        },
    )
