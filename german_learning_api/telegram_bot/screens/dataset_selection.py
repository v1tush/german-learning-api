import asyncio
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import PAGE_SIZE, current_locale, keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.texts import t


async def show_dataset_tags(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, requested_page: int
) -> None:
    locale = await current_locale(target, state)
    data = await state.get_data()
    selected = set(data["dataset_tags"])
    try:
        tags = sorted(await api.tags(target.from_user.id), key=lambda item: (item["name"].casefold(), item["id"]))
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "back"), "datasets:form:review")]]))
        return
    items, page, pages = page_of(tags, requested_page)
    rows = [
        [
            (
                f"{'✓ ' if item['id'] in selected else ''}{short_button_value(item['name'], 36)}",
                f"datasets:form:tag:{item['id']}:{page}",
            )
        ]
        for item in items
    ]
    rows += page_navigation("datasets:form:tags", page, pages)
    rows.append([(t(locale, "dataset_done"), "datasets:form:review")])
    body = t(
        locale,
        "dataset_tags_title",
        name=escape(data["dataset_name"]),
        count=str(len(tags)),
        page=str(page + 1),
        pages=str(pages),
    )
    if not tags:
        body += f"\n\n{t(locale, 'tags_empty')}"
    await show(target, body, keyboard(rows))


async def show_dataset_words(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, requested_page: int
) -> None:
    locale = await current_locale(target, state)
    data = await state.get_data()
    selected = set(data["dataset_extra_words"])
    try:
        words = sorted(await api.user_words(target.from_user.id), key=lambda item: item["id"], reverse=True)
        items, page, pages = page_of(words, requested_page)
        catalogue = await asyncio.gather(*(api.word(target.from_user.id, item["word_id"]) for item in items))
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "back"), "datasets:form:review")]]))
        return
    rows = [
        [
            (
                f"{'✓ ' if item['id'] in selected else ''}{index + page * PAGE_SIZE + 1}. {short_button_value(word['word'], 30)}",
                f"datasets:form:word:{item['id']}:{page}",
            )
        ]
        for index, (item, word) in enumerate(zip(items, catalogue, strict=True))
    ]
    rows += page_navigation("datasets:form:words", page, pages)
    rows.append([(t(locale, "dataset_done"), "datasets:form:review")])
    body = t(
        locale,
        "dataset_words_title",
        name=escape(data["dataset_name"]),
        count=str(len(words)),
        page=str(page + 1),
        pages=str(pages),
    )
    if not words:
        body += f"\n\n{t(locale, 'words_empty')}"
    await show(target, body, keyboard(rows))
