from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, reset_navigation_state, show
from telegram_bot.screens.word_addition import show_part_of_speech, show_spelling, show_translation_choices
from telegram_bot.screens.words import show_words
from telegram_bot.states import WordAddition
from telegram_bot.texts import t
from telegram_bot.word_addition import PARTS_OF_SPEECH, normalize_text

router = Router()


@router.callback_query(F.data == "words:add")
async def start_word_addition(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    try:
        profile = await api.profile(callback.from_user.id)
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    locale = profile["current_using_language"]
    await state.clear()
    await state.set_state(WordAddition.spelling)
    await state.update_data(
        locale=locale,
        learning_language=profile["current_learning_language"],
        using_language=locale,
    )
    await show_spelling(callback, locale)


@router.message(WordAddition.spelling)
async def receive_spelling(message: Message, state: FSMContext) -> None:
    locale = await current_locale(message, state)
    spelling = normalize_text(message.text or "")
    if not 1 <= len(spelling) <= 255:
        await message.answer(t(locale, "add_spelling_invalid"))
        return
    await state.update_data(spelling=spelling)
    await state.set_state(WordAddition.part_of_speech)
    await show_part_of_speech(message, await state.get_data())


@router.callback_query(F.data == "words:add:back:spelling")
async def back_to_spelling(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != WordAddition.part_of_speech.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await state.set_state(WordAddition.spelling)
    await show_spelling(callback, await current_locale(callback, state))


@router.callback_query(F.data.startswith("words:add:pos:"))
async def choose_part_of_speech(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != WordAddition.part_of_speech.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    part = callback.data.rsplit(":", 1)[-1]
    if part not in PARTS_OF_SPEECH:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    locale = data["locale"]
    try:
        word = await api.create_word(callback.from_user.id, data["spelling"], data["learning_language"], part)
        personal_words = await api.user_words(callback.from_user.id)
        existing = next((item for item in personal_words if item["word_id"] == word["id"]), None)
        if existing is None:
            translations = (await api.word_translations(callback.from_user.id, word["id"]))["translations"]
    except ApiError, ApiUnavailable, KeyError, TypeError:
        await show(
            callback,
            t(locale, "service_error"),
            keyboard(
                [
                    [(t(locale, "add_retry"), f"words:add:pos:{part}")],
                    [(t(locale, "cancel"), "words:add:cancel")],
                ]
            ),
        )
        return
    if existing is not None:
        await reset_navigation_state(state)
        await show(
            callback,
            t(locale, "add_exists"),
            keyboard(
                [
                    [(t(locale, "add_open_existing"), f"words:item:{existing['id']}:0:all")],
                    [(t(locale, "back_to_words"), "words:open:0")],
                ]
            ),
        )
        return
    await state.update_data(
        part_of_speech=part,
        word_id=word["id"],
        available_translations=translations,
        selected_base_ids=[],
        custom_translation=None,
        primary_keys=[],
    )
    await state.set_state(WordAddition.translations)
    await show_translation_choices(callback, await state.get_data())


@router.callback_query(F.data == "words:add:back:pos")
async def back_to_part_of_speech(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != WordAddition.translations.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await state.set_state(WordAddition.part_of_speech)
    await show_part_of_speech(callback, await state.get_data())


@router.callback_query(F.data == "words:add:cancel")
async def cancel_word_addition(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() not in {item.state for item in WordAddition.__states__}:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await reset_navigation_state(state)
    await show_words(callback, state, api, 0)
