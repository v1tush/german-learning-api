from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, show
from telegram_bot.screens.profile import show_profile
from telegram_bot.states import ProfileEdit
from telegram_bot.texts import t

router = Router()


async def save_text_profile(message: Message, state: FSMContext, api: WozziApi, field: str) -> None:
    locale = await current_locale(message, state)
    value = (message.text or "").strip()
    if field == "username" and not 1 <= len(value) <= 30:
        await message.answer(t(locale, "username_invalid"))
        return
    if field == "email" and (not value or len(value) > 254):
        await message.answer(t(locale, "email_invalid"))
        return
    try:
        profile = await api.update_profile(message.from_user.id, {field: value})
    except ApiError as error:
        if error.detail in ("username_already_exists", "email_already_exists", "invalid_email"):
            key = {
                "username_already_exists": "username_taken",
                "email_already_exists": "email_taken",
                "invalid_email": "email_invalid",
            }[error.detail]
            await message.answer(t(locale, key))
        else:
            await message.answer(t(locale, "service_error"))
        return
    except ApiUnavailable:
        await message.answer(t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(message, state, profile, api, t(profile["current_using_language"], "saved"))


@router.message(ProfileEdit.username)
async def change_username(message: Message, state: FSMContext, api: WozziApi) -> None:
    await save_text_profile(message, state, api, "username")


@router.message(ProfileEdit.email)
async def change_email(message: Message, state: FSMContext, api: WozziApi) -> None:
    await save_text_profile(message, state, api, "email")


@router.callback_query(F.data == "profile:email:ask-delete")
async def ask_remove_email(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    data = await state.get_data()
    if await state.get_state() != ProfileEdit.email.state or not data.get("edit_value"):
        await callback.answer(t(locale, "stale_action"))
        return
    await state.set_state(ProfileEdit.email_delete_confirmation)
    await show(
        callback,
        t(locale, "email_delete_confirm", email=escape(data["edit_value"])),
        keyboard(
            [
                [(t(locale, "delete"), "profile:email:delete")],
                [(t(locale, "back"), "profile:edit:email")],
            ]
        ),
    )


@router.callback_query(F.data == "profile:email:delete")
async def remove_email(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != ProfileEdit.email_delete_confirmation.state:
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        profile = await api.update_profile(callback.from_user.id, {"email": None})
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, api, t(locale, "saved"))
