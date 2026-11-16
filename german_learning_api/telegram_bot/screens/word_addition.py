from html import escape

from aiogram.enums import ButtonStyle
from aiogram.types import CallbackQuery, Message

from telegram_bot.common import keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.texts import language_name, t
from telegram_bot.word_addition import PARTS_OF_SPEECH, chosen_translations


def action_buttons(locale: str, back: str) -> list[list[tuple[str, str]]]:
    return [[(t(locale, "back"), back), (t(locale, "cancel"), "words:add:cancel")]]


async def show_spelling(target: Message | CallbackQuery, locale: str) -> None:
    await show(target, t(locale, "add_spelling_prompt"), keyboard([[(t(locale, "cancel"), "words:add:cancel")]]))


async def show_part_of_speech(target: Message | CallbackQuery, data: dict) -> None:
    locale = data["locale"]
    rows = [[(t(locale, f"word_pos_{part}"), f"words:add:pos:{part}")] for part in PARTS_OF_SPEECH]
    rows += action_buttons(locale, "words:add:back:spelling")
    await show(
        target,
        t(
            locale,
            "add_pos_prompt",
            word=escape(data["spelling"]),
            language=language_name(locale, data["learning_language"]),
        ),
        keyboard(rows),
    )


async def show_translation_choices(
    target: Message | CallbackQuery, data: dict, page: int = 0, notice: str = ""
) -> None:
    locale = data["locale"]
    translations = data.get("available_translations", [])
    items, page, pages = page_of(translations, page)
    selected = set(data.get("selected_base_ids", []))
    rows = [
        [
            (
                f"{'✓ ' if item['id'] in selected else ''}{short_button_value(item['value'], 48)}",
                f"words:add:translation:{item['id']}:{page}",
            )
        ]
        for item in items
    ]
    rows += page_navigation("words:add:page", page, pages)
    rows.append([(t(locale, "add_suggest"), "words:add:suggest", ButtonStyle.PRIMARY)])
    rows.append([(t(locale, "add_custom_button"), "words:add:custom", ButtonStyle.PRIMARY)])
    if data.get("custom_translation"):
        rows.append([(t(locale, "add_custom_remove"), "words:add:custom:remove", ButtonStyle.DANGER)])
    if chosen_translations(data):
        rows.append([(t(locale, "add_next"), "words:add:next", ButtonStyle.SUCCESS)])
    else:
        rows.append([(t(locale, "add_without_translation"), "words:add:without", ButtonStyle.PRIMARY)])
    rows += action_buttons(locale, "words:add:back:pos")
    body = t(
        locale,
        "add_translations_prompt",
        word=escape(data["spelling"]),
        count=str(len(selected)),
        language=language_name(locale, data["using_language"]),
    )
    if custom := data.get("custom_translation"):
        body += "\n" + t(locale, "add_custom_current", value=escape(custom))
    if not translations:
        body += "\n\n" + t(locale, "add_no_suggestions")
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    await show(target, body, keyboard(rows))


async def show_custom_prompt(target: Message | CallbackQuery, data: dict) -> None:
    locale = data["locale"]
    await show(target, t(locale, "add_custom_prompt"), keyboard(action_buttons(locale, "words:add:back:translations")))


async def show_primary_choices(target: Message | CallbackQuery, data: dict, notice: str = "") -> None:
    locale = data["locale"]
    selected = set(data.get("primary_keys", []))
    rows = [
        [
            (
                f"{'✓ ' if item['key'] in selected else ''}{short_button_value(item['value'], 48)}",
                f"words:add:primary:{item['key']}",
            )
        ]
        for item in chosen_translations(data)
    ]
    if selected:
        rows.append([(t(locale, "add_next"), "words:add:review", ButtonStyle.SUCCESS)])
    rows += action_buttons(locale, "words:add:back:translations")
    body = t(locale, "add_primary_prompt", count=str(len(selected)))
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    await show(target, body, keyboard(rows))


async def show_confirmation(target: Message | CallbackQuery, data: dict, notice: str = "") -> None:
    locale = data["locale"]
    primaries = set(data.get("primary_keys", []))
    translations = chosen_translations(data)
    lines = [
        f"{'⭐ ' if item['key'] in primaries else '• '}{escape(item['value'])}"
        + (f" ({t(locale, 'add_custom_label')})" if item["custom"] else "")
        for item in translations
    ]
    body = t(
        locale,
        "add_confirmation",
        word=escape(data["spelling"]),
        language=language_name(locale, data["learning_language"]),
        part=t(locale, f"word_pos_{data['part_of_speech']}"),
        translations="\n".join(lines) if lines else t(locale, "add_no_translation"),
    )
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    back = "words:add:back:primaries" if translations else "words:add:back:translations"
    rows = [[(t(locale, "add_save"), "words:add:save", ButtonStyle.SUCCESS)]] + action_buttons(locale, back)
    await show(target, body, keyboard(rows))
