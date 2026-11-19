import asyncio
from html import escape

from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, show
from telegram_bot.texts import t


def preview(names: list[str], locale: str, total: int | None = None) -> str:
    if not names:
        return t(locale, "dataset_none")
    shown = ", ".join(escape(name) for name in names[:3])
    remaining = (total if total is not None else len(names)) - 3
    return shown + (f" +{remaining}" if remaining > 0 else "")


async def show_dataset_name_prompt(target: Message | CallbackQuery, state: FSMContext, notice: str = "") -> None:
    locale = await current_locale(target, state)
    data = await state.get_data()
    body = t(locale, "dataset_name_prompt")
    if data.get("dataset_name"):
        body += "\n\n" + t(locale, "dataset_current_name", name=escape(data["dataset_name"]))
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    back = "datasets:form:review" if data.get("dataset_name") else "datasets:form:cancel"
    await show(target, body, keyboard([[(t(locale, "back"), back)], [(t(locale, "cancel"), "datasets:form:cancel")]]))


async def show_dataset_editor(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, notice: str = ""
) -> None:
    locale = await current_locale(target, state)
    data = await state.get_data()
    tag_ids = set(data["dataset_tags"])
    extra_ids = set(data["dataset_extra_words"])
    try:
        tags = await api.tags(target.from_user.id)
        user_words = await api.user_words(target.from_user.id)
        available_tag_ids = {item["id"] for item in tags}
        available_word_ids = {item["id"] for item in user_words}
        valid_tag_ids = tag_ids & available_tag_ids
        valid_extra_ids = extra_ids & available_word_ids
        if valid_tag_ids != tag_ids or valid_extra_ids != extra_ids:
            tag_ids, extra_ids = valid_tag_ids, valid_extra_ids
            await state.update_data(dataset_tags=sorted(tag_ids), dataset_extra_words=sorted(extra_ids))
        selected_words = [item for item in user_words if item["id"] in extra_ids]
        catalogue = await asyncio.gather(
            *(api.word(target.from_user.id, item["word_id"]) for item in selected_words[:3])
        )
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "cancel"), "datasets:form:cancel")]]))
        return
    tag_names = [item["name"] for item in tags if item["id"] in tag_ids]
    word_names = [item["word"] for item in catalogue]
    body = t(
        locale,
        "dataset_editor",
        title=t(locale, "dataset_editor_existing" if data.get("dataset_id") else "dataset_editor_new"),
        name=escape(data["dataset_name"]),
        tag_count=str(len(tag_ids)),
        tags=preview(tag_names, locale),
        word_count=str(len(extra_ids)),
        words=preview(word_names, locale, len(extra_ids)),
    )
    if notice:
        body = f"{escape(notice)}\n\n{body}"
    rows = [
        [(t(locale, "dataset_change_name"), "datasets:form:name")],
        [(t(locale, "dataset_choose_tags"), "datasets:form:tags:0")],
        [(t(locale, "dataset_choose_words"), "datasets:form:words:0")],
        [(t(locale, "dataset_save"), "datasets:form:save", ButtonStyle.SUCCESS)],
        [(t(locale, "cancel"), "datasets:form:cancel")],
    ]
    await show(target, body, keyboard(rows))
