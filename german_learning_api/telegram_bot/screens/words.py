import asyncio
from html import escape

from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import PAGE_SIZE, current_locale, keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.texts import language_name, t


def has_personal_translation(user_word: dict) -> bool:
    selection = user_word.get("translation_selection") or {}
    return bool(selection.get("base_translations") or selection.get("custom_translation"))


def selected_translation_lines(user_word: dict, locale: str) -> str:
    selection = user_word.get("translation_selection") or {}
    lines = [
        f"{'⭐' if item.get('is_card_primary') else '•'} {escape(item['value'])}"
        for item in selection.get("base_translations", [])
    ]
    if custom := selection.get("custom_translation"):
        marker = "⭐" if selection.get("custom_is_card_primary") else "•"
        lines.append(f"{marker} {escape(custom)} ({t(locale, 'add_custom_label')})")
    return "\n".join(lines) if lines else t(locale, "word_no_translations")


async def show_words(
    target: Message | CallbackQuery,
    state: FSMContext,
    api: WozziApi,
    requested_page: int,
    *,
    only_translated: bool = False,
    notice: str = "",
) -> None:
    locale = await current_locale(target, state)
    try:
        all_words = await api.user_words(target.from_user.id)
        words = sorted(
            (item for item in all_words if not only_translated or has_personal_translation(item)),
            key=lambda item: item["id"],
            reverse=True,
        )
        items, page, pages = page_of(words, requested_page)
        catalogue = await asyncio.gather(*(api.word(target.from_user.id, item["word_id"]) for item in items))
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "main_menu_button"), "menu:open")]]))
        return
    mode = "translated" if only_translated else "all"
    rows = [
        [
            (
                f"{index + page * PAGE_SIZE + 1}. {short_button_value(word['word'], 32)}",
                f"words:item:{item['id']}:{page}:{mode}",
            )
        ]
        for index, (item, word) in enumerate(zip(items, catalogue, strict=True))
    ]
    rows += page_navigation("words:translated" if only_translated else "words:open", page, pages)
    rows.append(
        [
            (f"{'✓ ' if not only_translated else ''}{t(locale, 'words_filter_all')}", "words:open:0"),
            (f"{'✓ ' if only_translated else ''}{t(locale, 'words_filter_translated')}", "words:translated:0"),
        ]
    )
    rows.append([(t(locale, "add_word_button"), "words:add")])
    rows.append([(t(locale, "main_menu_button"), "menu:open")])
    body = t(locale, "words_title", count=str(len(words)), page=str(page + 1), pages=str(pages))
    if notice:
        body += f"\n\n{escape(notice)}"
    if not words:
        body += f"\n\n{t(locale, 'words_translated_empty' if only_translated else 'words_empty')}"
    await show(target, body, keyboard(rows))


async def show_word_detail(
    target: Message | CallbackQuery,
    state: FSMContext,
    api: WozziApi,
    user_word_id: int,
    page: int,
    *,
    only_translated: bool = False,
    notice: str = "",
) -> None:
    locale = await current_locale(target, state)
    try:
        user_word = await api.user_word(target.from_user.id, user_word_id)
        word = await api.word(target.from_user.id, user_word["word_id"])
        inflections = await api.word_inflections(target.from_user.id, user_word["word_id"])
        tags = await api.tags(target.from_user.id)
    except ApiError, ApiUnavailable:
        await show_words(target, state, api, page, only_translated=only_translated)
        return
    forms = ""
    if inflections:
        form_lines = []
        for item in inflections:
            form_name = t(locale, f"word_form_{item['type']}")
            form_lines.append(f"• {form_name}: {escape(item['value'])}")
        forms = "\n\n" + t(locale, "word_forms", values="\n".join(form_lines))
    body = t(
        locale,
        "word_detail",
        word=escape(word["word"]),
        language=language_name(locale, word["language"]),
        part=t(locale, f"word_pos_{word['part_of_speech']}"),
        forms=forms,
        translations=selected_translation_lines(user_word, locale),
        status=t(locale, f"status_{user_word['status']}"),
        hint=escape(user_word.get("user_hint") or t(locale, "empty")),
    )
    selected = set(user_word.get("tags") or [])
    names = [escape(tag["name"]) for tag in tags if tag["id"] in selected]
    shown = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
    body += "\n\n" + t(locale, "word_tags", tags=shown or t(locale, "word_tags_empty"))
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    back = "words:translated" if only_translated else "words:open"
    mode = "translated" if only_translated else "all"
    await show(
        target,
        body,
        keyboard(
            [
                [(t(locale, "back_to_words"), f"{back}:{page}")],
                [
                    (
                        t(locale, "word_delete"),
                        f"words:delete:ask:{user_word_id}:{page}:{mode}",
                        ButtonStyle.DANGER,
                    )
                ],
                [
                    (
                        t(locale, "word_manage_tags"),
                        f"tags:word:{user_word_id}:{page}:{'t' if only_translated else 'a'}:0",
                    )
                ],
                [(t(locale, "main_menu_button"), "menu:open")],
            ]
        ),
    )
