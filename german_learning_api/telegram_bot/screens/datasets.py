from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, page_navigation, page_of, short_button_value, show
from telegram_bot.texts import t


async def show_datasets(target: Message | CallbackQuery, state: FSMContext, api: WozziApi, requested_page: int) -> None:
    locale = await current_locale(target, state)
    try:
        datasets = await api.datasets(target.from_user.id)
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "main_menu_button"), "menu:open")]]))
        return
    items, page, pages = page_of(datasets, requested_page)
    rows = [[(short_button_value(item["name"], 36), f"datasets:item:{item['id']}:0:{page}")] for item in items]
    rows += page_navigation("datasets:open", page, pages)
    rows.append([(t(locale, "main_menu_button"), "menu:open")])
    body = t(locale, "datasets_title", count=str(len(datasets)), page=str(page + 1), pages=str(pages))
    if not datasets:
        body += f"\n\n{t(locale, 'datasets_empty')}"
    await show(target, body, keyboard(rows))


async def show_dataset_detail(
    target: Message | CallbackQuery,
    state: FSMContext,
    api: WozziApi,
    dataset_id: int,
    requested_page: int,
    back_page: int,
) -> None:
    locale = await current_locale(target, state)
    try:
        dataset = await api.dataset(target.from_user.id, dataset_id)
        words = await api.dataset_words(target.from_user.id, dataset_id)
    except ApiError, ApiUnavailable:
        await show_datasets(target, state, api, back_page)
        return
    items, page, pages = page_of(words, requested_page)
    body = t(
        locale,
        "dataset_detail",
        name=escape(dataset["name"]),
        count=str(len(words)),
        page=str(page + 1),
        pages=str(pages),
    )
    body += "\n\n" + ("\n".join(f"• {escape(item['word'])}" for item in items) if words else t(locale, "dataset_empty"))
    rows = page_navigation(f"datasets:item:{dataset_id}", page, pages)
    rows = [[(label, f"{data}:{back_page}") for label, data in row] for row in rows]
    rows.extend(
        [
            [(t(locale, "back_to_datasets"), f"datasets:open:{back_page}")],
            [(t(locale, "main_menu_button"), "menu:open")],
        ]
    )
    await show(target, body, keyboard(rows))
