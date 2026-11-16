from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, reset_navigation_state
from telegram_bot.screens.word_deletion import show_delete_confirmation
from telegram_bot.screens.words import show_word_detail, show_words
from telegram_bot.states import WordDeletion
from telegram_bot.texts import t

router = Router()


@router.callback_query(F.data.startswith("words:delete:ask:"))
async def ask_delete_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    parts = callback.data.split(":")
    if len(parts) != 6 or parts[5] not in {"all", "translated"}:
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        user_word_id, page = int(parts[3]), int(parts[4])
    except ValueError:
        await callback.answer(t(locale, "stale_action"))
        return
    if user_word_id < 1 or page < 0:
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        user_word = await api.user_word(callback.from_user.id, user_word_id)
        word = await api.word(callback.from_user.id, user_word["word_id"])
        spelling = word["word"]
    except ApiError, ApiUnavailable, KeyError, TypeError:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await state.set_state(WordDeletion.confirmation)
    await state.update_data(
        delete_user_word_id=user_word_id,
        delete_page=page,
        delete_only_translated=parts[5] == "translated",
    )
    await show_delete_confirmation(callback, locale, spelling)


@router.callback_query(F.data == "words:delete:cancel")
async def cancel_delete_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    data = await state.get_data()
    if await state.get_state() != WordDeletion.confirmation.state or "delete_user_word_id" not in data:
        await callback.answer(t(locale, "stale_action"))
        return
    await reset_navigation_state(state)
    await show_word_detail(
        callback,
        state,
        api,
        data["delete_user_word_id"],
        data["delete_page"],
        only_translated=data["delete_only_translated"],
    )


@router.callback_query(F.data == "words:delete:confirm")
async def delete_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    data = await state.get_data()
    if await state.get_state() != WordDeletion.confirmation.state or "delete_user_word_id" not in data:
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        await api.delete_user_word(callback.from_user.id, data["delete_user_word_id"])
    except ApiError as error:
        if error.status != 404:
            await callback.answer(t(locale, "service_error"), show_alert=True)
            return
    except ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    await show_words(
        callback,
        state,
        api,
        data["delete_page"],
        only_translated=data["delete_only_translated"],
        notice=t(locale, "word_deleted"),
    )
