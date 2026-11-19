from html import escape

from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.texts import t


async def show_tags(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, requested_page: int, notice: str = ""
) -> None:
    locale = await current_locale(target, state)
    try:
        tags = sorted(await api.tags(target.from_user.id), key=lambda item: (item["name"].casefold(), item["id"]))
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "main_menu_button"), "menu:open")]]))
        return
    items, page, pages = page_of(tags, requested_page)
    rows = [[(short_button_value(item["name"], 36), f"tags:item:{item['id']}:0:{page}")] for item in items]
    rows += page_navigation("tags:open", page, pages)
    rows.append([(t(locale, "tag_create"), f"tags:create:list:{page}", ButtonStyle.SUCCESS)])
    rows.append([(t(locale, "main_menu_button"), "menu:open")])
    body = t(locale, "tags_title", count=str(len(tags)), page=str(page + 1), pages=str(pages))
    if notice:
        body += f"\n\n{escape(notice)}"
    if not tags:
        body += f"\n\n{t(locale, 'tags_empty')}"
    await show(target, body, keyboard(rows))


async def show_tag_detail(
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
        words = await api.tag_words(target.from_user.id, tag_id)
    except ApiError, ApiUnavailable:
        await show_tags(target, state, api, back_page)
        return
    items, page, pages = page_of(words, requested_page)
    body = t(
        locale,
        "tag_detail",
        name=escape(tag["name"]),
        count=str(len(words)),
        page=str(page + 1),
        pages=str(pages),
    )
    if notice:
        body += f"\n\n{escape(notice)}"
    body += "\n\n" + (
        "\n".join(f"• {escape(item['word'])}" for item in items) if words else t(locale, "tag_words_empty")
    )
    rows = page_navigation(f"tags:item:{tag_id}", page, pages)
    rows = [[(label, f"{data}:{back_page}") for label, data in row] for row in rows]
    rows.extend(
        [
            [(t(locale, "tag_manage_words"), f"tags:pick:{tag_id}:0:{back_page}")],
            [(t(locale, "tag_delete"), f"tags:delete:ask:{tag_id}:{page}:{back_page}", ButtonStyle.DANGER)],
            [(t(locale, "back_to_tags"), f"tags:open:{back_page}")],
            [(t(locale, "main_menu_button"), "menu:open")],
        ]
    )
    await show(target, body, keyboard(rows))
