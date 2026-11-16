from telegram_bot.locales.de import TEXTS as DE_TEXTS
from telegram_bot.locales.en import TEXTS as EN_TEXTS
from telegram_bot.locales.ru import TEXTS as RU_TEXTS

LANGUAGES = ("ru", "en", "de")
LANGUAGE_NAMES = {"ru": "Русский", "en": "English", "de": "Deutsch"}
LANGUAGE_LABELS = {
    "ru": {"ru": "Русский", "en": "Английский", "de": "Немецкий"},
    "en": {"ru": "Russian", "en": "English", "de": "German"},
    "de": {"ru": "Russisch", "en": "Englisch", "de": "Deutsch"},
}

TEXTS = {"ru": RU_TEXTS, "en": EN_TEXTS, "de": DE_TEXTS}


def locale_from_telegram(code: str | None) -> str | None:
    locale = (code or "").lower().split("-", 1)[0].split("_", 1)[0]
    return locale if locale in LANGUAGES else None


def language_name(locale: str, code: str) -> str:
    return LANGUAGE_LABELS.get(locale, LANGUAGE_LABELS["en"]).get(code, code)


def t(locale: str, key: str, **values: str) -> str:
    return TEXTS.get(locale, TEXTS["en"])[key].format(**values)
