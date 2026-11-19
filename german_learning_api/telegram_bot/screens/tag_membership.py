import asyncio
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import PAGE_SIZE, current_locale, keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.screens.tags import show_tag_detail, show_tags
from telegram_bot.texts import t


async def show_tag_word_picker(
    target: Message | CallbackQuery,
    state: FSMContext,
    api: WozziApi,
    tag_id: int,
    requested_page: int,
    back_page: int,
    notice: str = "",
) -> None:
    locale = await current_locale(target, state)
    try:
        tag = await api.tag(target.from_user.id, tag_id)
        tagged = {item["id"] for item in await api.tag_words(target.from_user.id, tag_id)}
        words = sorted(await api.user_words(target.from_user.id), key=lambda item: item["id"], reverse=True)
        items, page, pages = page_of(words, requested_page)
        catalogue = await asyncio.gather(*(api.word(target.from_user.id, item["word_id"]) for item in items))
    except ApiError, ApiUnavailable:
        await show_tag_detail(target, state, api, tag_id, 0, back_page)
        return
    rows = [
        [
            (
                f"{'✓ ' if item['id'] in tagged else ''}{index + page * PAGE_SIZE + 1}. {short_button_value(word['word'], 30)}",
                f"tags:tw:{'r' if item['id'] in tagged else 'a'}:{tag_id}:{item['id']}:{page}:{back_page}",
            )
        ]
        for index, (item, word) in enumerate(zip(items, catalogue, strict=True))
    ]
    navigation = page_navigation(f"tags:pick:{tag_id}", page, pages)
    rows += [[(label, f"{data}:{back_page}") for label, data in row] for row in navigation]
    rows.append([(t(locale, "back_to_tag"), f"tags:item:{tag_id}:0:{back_page}")])
    body = t(
        locale, "tag_word_picker", name=escape(tag["name"]), count=str(len(words)), page=str(page + 1), pages=str(pages)
    )
    if notice:
        body += f"\n\n{escape(notice)}"
    if not words:
        body += f"\n\n{t(locale, 'words_empty')}"
    await show(target, body, keyboard(rows))


async def show_word_tag_picker(
    target: Message | CallbackQuery,
    state: FSMContext,
    api: WozziApi,
    user_word_id: int,
    word_page: int,
    mode: str,
    requested_page: int,
    notice: str = "",
) -> None:
    locale = await current_locale(target, state)
    try:
        user_word = await api.user_word(target.from_user.id, user_word_id)
        word = await api.word(target.from_user.id, user_word["word_id"])
        tags = sorted(await api.tags(target.from_user.id), key=lambda item: (item["name"].casefold(), item["id"]))
    except ApiError, ApiUnavailable:
        await show_tags(target, state, api, 0)
        return
    selected = set(user_word["tags"])
    items, page, pages = page_of(tags, requested_page)
    rows = [
        [
            (
                f"{'✓ ' if item['id'] in selected else ''}{short_button_value(item['name'], 36)}",
                f"tags:wt:{'r' if item['id'] in selected else 'a'}:{user_word_id}:{item['id']}:{word_page}:{mode}:{page}",
            )
        ]
        for item in items
    ]
    rows += page_navigation(f"tags:word:{user_word_id}:{word_page}:{mode}", page, pages)
    rows.append([(t(locale, "tag_create"), f"tags:create:word:{user_word_id}:{word_page}:{mode}:{page}")])
    rows.append(
        [(t(locale, "back_to_word"), f"words:item:{user_word_id}:{word_page}:{'translated' if mode == 't' else 'all'}")]
    )
    body = t(
        locale, "word_tag_picker", word=escape(word["word"]), count=str(len(tags)), page=str(page + 1), pages=str(pages)
    )
    if notice:
        body += f"\n\n{escape(notice)}"
    if not tags:
        body += f"\n\n{t(locale, 'tags_empty')}"
    await show(target, body, keyboard(rows))
