from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, reset_navigation_state
from telegram_bot.screens.word_addition import show_confirmation, show_primary_choices
from telegram_bot.screens.words import show_word_detail
from telegram_bot.states import WordAddition
from telegram_bot.texts import t
from telegram_bot.word_addition import chosen_translations, selection_payload

router = Router()


@router.callback_query(F.data.startswith("words:add:primary:"))
async def toggle_primary(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != WordAddition.primaries.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    key = callback.data.removeprefix("words:add:primary:")
    if key not in {item["key"] for item in chosen_translations(data)}:
        await callback.answer(t(data["locale"], "stale_action"))
        return
    selected = list(data.get("primary_keys", []))
    if key in selected:
        selected.remove(key)
    elif len(selected) < 2:
        selected.append(key)
    else:
        await show_primary_choices(callback, data, t(data["locale"], "add_two_limit"))
        return
    await state.update_data(primary_keys=selected)
    await show_primary_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:review")
async def review_word(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != WordAddition.primaries.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    if not data.get("primary_keys"):
        await callback.answer(t(data["locale"], "stale_action"))
        return
    await state.set_state(WordAddition.confirmation)
    await show_confirmation(callback, data)


@router.callback_query(F.data == "words:add:back:primaries")
async def back_to_primaries(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != WordAddition.confirmation.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await state.set_state(WordAddition.primaries)
    await show_primary_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:save")
async def save_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != WordAddition.confirmation.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    locale = data["locale"]
    selection = selection_payload(data)
    if selection is not None and not data.get("primary_keys"):
        await callback.answer(t(locale, "stale_action"))
        return
    try:
        existing = next(
            (item for item in await api.user_words(callback.from_user.id) if item["word_id"] == data["word_id"]),
            None,
        )
        user_word = existing or await api.add_user_word(callback.from_user.id, data["word_id"], selection)
    except ApiError as error:
        notice = t(locale, "add_selection_invalid") if error.status == 422 else t(locale, "service_error")
        await show_confirmation(callback, data, notice)
        return
    except ApiUnavailable:
        await show_confirmation(callback, data, t(locale, "service_error"))
        return
    await reset_navigation_state(state)
    notice = t(locale, "add_exists") if existing else t(locale, "add_saved")
    await show_word_detail(callback, state, api, user_word["id"], 0, notice=notice)
