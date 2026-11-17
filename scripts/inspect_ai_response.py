import argparse
import json
import os
import sys

import django
import openai


def main() -> int:
    parser = argparse.ArgumentParser(description="Показать ответ модели для сохранённого слова.")
    parser.add_argument("word_id", type=int, help="ID слова в базе API")
    parser.add_argument("target_language", help="Язык перевода, например ru")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "german_learning_api.settings")
    django.setup()

    from translations.integrations.yandex_ai import call_api, word_to_dict
    from words.models import Word

    try:
        word = Word.objects.get(pk=args.word_id)
    except Word.DoesNotExist:
        print(f"Слово с ID {args.word_id} не найдено.", file=sys.stderr)
        return 2

    word_data = word_to_dict(word)
    word_data["target_language"] = args.target_language
    try:
        response = call_api(word_data)
    except openai.APIStatusError as error:
        from django.conf import settings

        body = error.response.text
        if settings.YANDEX_CLOUD_API_KEY:
            body = body.replace(settings.YANDEX_CLOUD_API_KEY, "[скрыто]")
        try:
            response_body = json.loads(body)
        except json.JSONDecodeError:
            response_body = body
        print(
            json.dumps({"http_status": error.status_code, "response_body": response_body}, ensure_ascii=False, indent=2)
        )
        return 1
    except openai.APIError as error:
        print(json.dumps({"error_type": type(error).__name__, "message": str(error)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
