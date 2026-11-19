from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, reset_navigation_state
from telegram_bot.screens.tag_membership import show_tag_word_picker, show_word_tag_picker
from telegram_bot.texts import t

router = Router()


@router.callback_query(F.data.startswith("tags:pick:"))
async def open_tag_word_picker(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, tag_id, page, back_page = callback.data.split(":")
    await reset_navigation_state(state)
    await show_tag_word_picker(callback, state, api, int(tag_id), int(page), int(back_page))


@router.callback_query(F.data.startswith("tags:word:"))
async def open_word_tag_picker(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, user_word_id, word_page, mode, page = callback.data.split(":")
    await reset_navigation_state(state)
    await show_word_tag_picker(callback, state, api, int(user_word_id), int(word_page), mode, int(page))


@router.callback_query(F.data.startswith("tags:tw:"))
async def change_tag_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, action, tag_id, user_word_id, page, back_page = callback.data.split(":")
    locale = await current_locale(callback, state)
    if await state.get_state():
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        method = api.add_tag_word if action == "a" else api.remove_tag_word
        await method(callback.from_user.id, int(tag_id), int(user_word_id))
    except ApiError, ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    notice = t(locale, "tag_word_added" if action == "a" else "tag_word_removed")
    await show_tag_word_picker(callback, state, api, int(tag_id), int(page), int(back_page), notice)


@router.callback_query(F.data.startswith("tags:wt:"))
async def change_word_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, action, user_word_id, tag_id, word_page, mode, page = callback.data.split(":")
    locale = await current_locale(callback, state)
    if await state.get_state():
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        method = api.add_tag_word if action == "a" else api.remove_tag_word
        await method(callback.from_user.id, int(tag_id), int(user_word_id))
    except ApiError, ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    notice = t(locale, "tag_word_added" if action == "a" else "tag_word_removed")
    await show_word_tag_picker(callback, state, api, int(user_word_id), int(word_page), mode, int(page), notice)
