from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale
from telegram_bot.screens.word_addition import (
    show_confirmation,
    show_custom_prompt,
    show_primary_choices,
    show_translation_choices,
)
from telegram_bot.states import WordAddition
from telegram_bot.texts import t
from telegram_bot.word_addition import chosen_translations, normalize_text

router = Router()


async def _is_translations_state(callback: CallbackQuery, state: FSMContext) -> bool:
    if await state.get_state() == WordAddition.translations.state:
        return True
    await callback.answer(t(await current_locale(callback, state), "stale_action"))
    return False


@router.callback_query(F.data.startswith("words:add:page:"))
async def translation_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    await show_translation_choices(callback, await state.get_data(), int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("words:add:translation:"))
async def toggle_translation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    _, _, _, translation_id, page = callback.data.split(":")
    translation_id = int(translation_id)
    data = await state.get_data()
    available = {item["id"]: item["value"] for item in data.get("available_translations", [])}
    allowed = set(available)
    if translation_id not in allowed:
        await callback.answer(t(data["locale"], "stale_action"))
        return
    selected = list(data.get("selected_base_ids", []))
    if translation_id in selected:
        selected.remove(translation_id)
    elif len(selected) < 5:
        custom = data.get("custom_translation")
        if custom and normalize_text(available[translation_id]).casefold() == normalize_text(custom).casefold():
            await show_translation_choices(callback, data, int(page), t(data["locale"], "add_custom_duplicate"))
            return
        selected.append(translation_id)
    else:
        await show_translation_choices(callback, data, int(page), t(data["locale"], "add_five_limit"))
        return
    primaries = [key for key in data.get("primary_keys", []) if key != f"base:{translation_id}"]
    await state.update_data(selected_base_ids=selected, primary_keys=primaries)
    await show_translation_choices(callback, await state.get_data(), int(page))


@router.callback_query(F.data == "words:add:suggest")
async def suggest_translations(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if not await _is_translations_state(callback, state):
        return
    data = await state.get_data()
    locale = data["locale"]
    try:
        response = await api.suggest_translations(callback.from_user.id, data["word_id"])
        translations = response["translations"]
    except ApiError, ApiUnavailable, KeyError, TypeError:
        await show_translation_choices(callback, data, notice=t(locale, "add_suggestions_unavailable"))
        return
    allowed = {item["id"] for item in translations}
    selected = [item for item in data.get("selected_base_ids", []) if item in allowed]
    allowed_primaries = {f"base:{item}" for item in selected}
    if data.get("custom_translation"):
        allowed_primaries.add("custom")
    primaries = [key for key in data.get("primary_keys", []) if key in allowed_primaries]
    await state.update_data(available_translations=translations, selected_base_ids=selected, primary_keys=primaries)
    notice = t(locale, "add_suggestions_unavailable") if response.get("status") != "success" else ""
    await show_translation_choices(callback, await state.get_data(), notice=notice)


@router.callback_query(F.data == "words:add:custom")
async def enter_custom_translation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    await state.set_state(WordAddition.custom_translation)
    await show_custom_prompt(callback, await state.get_data())


@router.message(WordAddition.custom_translation)
async def receive_custom_translation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    locale = data["locale"]
    custom = normalize_text(message.text or "")
    if not 1 <= len(custom) <= 500:
        await message.answer(t(locale, "add_custom_invalid"))
        return
    available = {item["id"]: item["value"] for item in data.get("available_translations", [])}
    if any(
        normalize_text(available[item]).casefold() == custom.casefold()
        for item in data["selected_base_ids"]
        if item in available
    ):
        await message.answer(t(locale, "add_custom_duplicate"))
        return
    await state.update_data(custom_translation=custom)
    await state.set_state(WordAddition.translations)
    await show_translation_choices(message, await state.get_data())


@router.callback_query(F.data == "words:add:custom:remove")
async def remove_custom_translation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    data = await state.get_data()
    await state.update_data(
        custom_translation=None,
        primary_keys=[key for key in data.get("primary_keys", []) if key != "custom"],
    )
    await show_translation_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:back:translations")
async def back_to_translations(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() not in {WordAddition.custom_translation.state, WordAddition.primaries.state}:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await state.set_state(WordAddition.translations)
    await show_translation_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:next")
async def finish_translation_selection(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    data = await state.get_data()
    allowed = {item["key"] for item in chosen_translations(data)}
    if not allowed:
        await callback.answer(t(data["locale"], "stale_action"))
        return
    await state.update_data(primary_keys=[key for key in data.get("primary_keys", []) if key in allowed])
    await state.set_state(WordAddition.primaries)
    await show_primary_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:without")
async def without_translation(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _is_translations_state(callback, state):
        return
    data = await state.get_data()
    if chosen_translations(data):
        await callback.answer(t(data["locale"], "stale_action"))
        return
    await state.set_state(WordAddition.confirmation)
    await show_confirmation(callback, data)
