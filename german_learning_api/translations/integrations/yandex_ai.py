import json

import openai
from django.conf import settings
from words.models import Word
from pathlib import Path


PROMPT_PATH = Path(__file__).parent / "word_translation_prompt"

client = openai.OpenAI(
    api_key=settings.YANDEX_CLOUD_API_KEY,
    base_url=settings.YANDEX_CLOUD_BASE_URL,
    project=settings.YANDEX_CLOUD_FOLDER,
    timeout=10.0,
    max_retries=1,
)

with PROMPT_PATH.open("r", encoding="utf-8") as file:
    BASE_PROMPT = file.read()

def word_to_dict(word: Word) -> dict:
    return {
        "word": word.word,
        "language": word.language,
        "part_of_speech": word.part_of_speech,
    }


def call_api(word_data):
    string_input = json.dumps(word_data, ensure_ascii=False)
    return client.responses.create(
        model=f"gpt://{settings.YANDEX_CLOUD_FOLDER}/{settings.YANDEX_CLOUD_MODEL}",
        instructions=BASE_PROMPT,
        input=string_input,
        temperature=0.2,
        max_output_tokens=500,
    )
