from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, show
from telegram_bot.screens.profile import show_profile
from telegram_bot.states import ProfileEdit
from telegram_bot.texts import t

router = Router()


@router.message(ProfileEdit.avatar)
async def change_avatar(message: Message, state: FSMContext, api: WozziApi, bot: Bot) -> None:
    locale = await current_locale(message, state)
    if not message.photo:
        await message.answer(t(locale, "avatar_missing"))
        return
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 2 * 1024 * 1024:
        await message.answer(t(locale, "avatar_large"))
        return
    try:
        image = BytesIO()
        await bot.download(photo, destination=image)
        if len(image.getbuffer()) > 2 * 1024 * 1024:
            await message.answer(t(locale, "avatar_large"))
            return
        profile = await api.upload_avatar(message.from_user.id, image.getvalue())
    except ApiError as error:
        key = "avatar_large" if error.status == 413 else "avatar_error"
        await message.answer(t(locale, key))
        return
    except ApiUnavailable, TelegramNetworkError:
        await message.answer(t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(message, state, profile, api, t(locale, "avatar_saved"))


@router.callback_query(F.data == "profile:avatar:ask-delete")
async def ask_remove_avatar(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != ProfileEdit.avatar.state:
        await callback.answer(t(locale, "stale_action"))
        return
    await state.set_state(ProfileEdit.avatar_delete_confirmation)
    await show(
        callback,
        t(locale, "avatar_delete_confirm"),
        keyboard(
            [
                [(t(locale, "delete"), "profile:avatar:delete")],
                [(t(locale, "back"), "profile:edit:avatar")],
            ]
        ),
    )


@router.callback_query(F.data == "profile:avatar:delete")
async def remove_avatar(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != ProfileEdit.avatar_delete_confirmation.state:
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        profile = await api.delete_avatar(callback.from_user.id)
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, api, t(locale, "avatar_deleted"))
