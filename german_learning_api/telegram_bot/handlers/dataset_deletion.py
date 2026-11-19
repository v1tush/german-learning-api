from html import escape

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, reset_navigation_state, show
from telegram_bot.screens.datasets import show_dataset_detail, show_datasets
from telegram_bot.states import DatasetDeletion
from telegram_bot.texts import t

router = Router()


@router.callback_query(F.data.startswith("datasets:delete:ask:"))
async def ask_delete_dataset(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, _, dataset_id, detail_page, back_page = callback.data.split(":")
    locale = await current_locale(callback, state)
    try:
        dataset = await api.dataset(callback.from_user.id, int(dataset_id))
    except ApiError, ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    await state.update_data(
        dataset_id=int(dataset_id), dataset_detail_page=int(detail_page), dataset_back_page=int(back_page)
    )
    await state.set_state(DatasetDeletion.confirmation)
    await show(
        callback,
        t(locale, "dataset_delete_confirm", name=escape(dataset["name"])),
        keyboard(
            [
                [(t(locale, "delete"), "datasets:delete:confirm", ButtonStyle.DANGER)],
                [(t(locale, "cancel"), "datasets:delete:cancel")],
            ]
        ),
    )


@router.callback_query(F.data == "datasets:delete:cancel")
async def cancel_delete_dataset(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != DatasetDeletion.confirmation.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    await reset_navigation_state(state)
    await show_dataset_detail(
        callback, state, api, data["dataset_id"], data["dataset_detail_page"], data["dataset_back_page"]
    )


@router.callback_query(F.data == "datasets:delete:confirm")
async def delete_dataset(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != DatasetDeletion.confirmation.state:
        await callback.answer(t(locale, "stale_action"))
        return
    data = await state.get_data()
    try:
        await api.delete_dataset(callback.from_user.id, data["dataset_id"])
    except ApiError as error:
        if error.status == 409 and error.detail == "dataset_in_use":
            await reset_navigation_state(state)
            await show_dataset_detail(
                callback,
                state,
                api,
                data["dataset_id"],
                data["dataset_detail_page"],
                data["dataset_back_page"],
                t(locale, "dataset_in_use"),
            )
            return
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    except ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    await show_datasets(callback, state, api, data["dataset_back_page"], t(locale, "dataset_deleted"))
