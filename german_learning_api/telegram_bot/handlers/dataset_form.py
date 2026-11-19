from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, reset_navigation_state
from telegram_bot.screens.dataset_editor import show_dataset_editor, show_dataset_name_prompt
from telegram_bot.screens.datasets import show_dataset_detail, show_datasets
from telegram_bot.states import DatasetForm
from telegram_bot.texts import t

router = Router()


async def form_is_active(callback: CallbackQuery, state: FSMContext) -> bool:
    if await state.get_state() in {DatasetForm.name.state, DatasetForm.review.state}:
        return True
    await callback.answer(t(await current_locale(callback, state), "stale_action"))
    return False


async def return_from_form(target: Message | CallbackQuery, state: FSMContext, api: WozziApi, data: dict) -> None:
    if dataset_id := data.get("dataset_id"):
        await show_dataset_detail(
            target, state, api, dataset_id, data["dataset_detail_page"], data["dataset_back_page"]
        )
    else:
        await show_datasets(target, state, api, data.get("dataset_back_page", 0))


@router.callback_query(F.data.startswith("datasets:create:"))
async def start_dataset_creation(callback: CallbackQuery, state: FSMContext) -> None:
    back_page = int(callback.data.rsplit(":", 1)[-1])
    await reset_navigation_state(state)
    await state.update_data(dataset_id=None, dataset_tags=[], dataset_extra_words=[], dataset_back_page=back_page)
    await state.set_state(DatasetForm.name)
    await show_dataset_name_prompt(callback, state)


@router.callback_query(F.data.startswith("datasets:edit:"))
async def start_dataset_edit(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, dataset_id, detail_page, back_page = callback.data.split(":")
    locale = await current_locale(callback, state)
    try:
        dataset = await api.dataset(callback.from_user.id, int(dataset_id))
    except ApiError, ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    await state.update_data(
        dataset_id=int(dataset_id),
        dataset_name=dataset["name"],
        dataset_tags=dataset["tags"],
        dataset_extra_words=dataset["extra_words"],
        dataset_detail_page=int(detail_page),
        dataset_back_page=int(back_page),
    )
    await state.set_state(DatasetForm.review)
    await show_dataset_editor(callback, state, api)


@router.callback_query(F.data == "datasets:form:name")
async def change_dataset_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not await form_is_active(callback, state):
        return
    await state.set_state(DatasetForm.name)
    await show_dataset_name_prompt(callback, state)


@router.message(DatasetForm.name)
async def receive_dataset_name(message: Message, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(message, state)
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        notice = t(locale, "dataset_name_empty" if not name else "dataset_name_too_long")
        await show_dataset_name_prompt(message, state, notice)
        return
    await state.update_data(dataset_name=name)
    await state.set_state(DatasetForm.review)
    await show_dataset_editor(message, state, api)


@router.callback_query(F.data == "datasets:form:review")
async def review_dataset(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if not await form_is_active(callback, state):
        return
    if not (await state.get_data()).get("dataset_name"):
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await state.set_state(DatasetForm.review)
    await show_dataset_editor(callback, state, api)


@router.callback_query(F.data == "datasets:form:save")
async def save_dataset(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != DatasetForm.review.state:
        await callback.answer(t(locale, "stale_action"))
        return
    data = await state.get_data()
    try:
        if dataset_id := data.get("dataset_id"):
            dataset = await api.update_dataset(
                callback.from_user.id,
                dataset_id,
                data["dataset_name"],
                sorted(data["dataset_tags"]),
                sorted(data["dataset_extra_words"]),
            )
        else:
            dataset = await api.create_dataset(
                callback.from_user.id,
                data["dataset_name"],
                sorted(data["dataset_tags"]),
                sorted(data["dataset_extra_words"]),
            )
    except ApiError as error:
        if error.status == 409:
            key = "dataset_exists"
        elif error.detail in {"invalid_tag_ids", "invalid_extra_word_ids"}:
            key = "dataset_invalid_selection"
        else:
            key = "service_error"
        await callback.answer(t(locale, key), show_alert=True)
        return
    except ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    notice = t(locale, "dataset_updated" if data.get("dataset_id") else "dataset_created")
    await show_dataset_detail(callback, state, api, dataset["id"], 0, data["dataset_back_page"], notice)


@router.callback_query(F.data == "datasets:form:cancel")
async def cancel_dataset_form(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if not await form_is_active(callback, state):
        return
    data = await state.get_data()
    await reset_navigation_state(state)
    await return_from_form(callback, state, api, data)
