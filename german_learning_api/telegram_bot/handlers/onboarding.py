from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, locale_buttons, show
from telegram_bot.screens.menu import home, show_main_menu
from telegram_bot.screens.onboarding import show_onboarding
from telegram_bot.states import Registration
from telegram_bot.texts import LANGUAGES, language_name, t

router = Router()


@router.callback_query(F.data.startswith("onboard:locale:"))
async def choose_onboarding_locale(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = callback.data.rsplit(":", 1)[-1]
    if locale not in LANGUAGES:
        await callback.answer()
        return
    try:
        profile = await api.profile(callback.from_user.id)
    except ApiError as error:
        if error.status != 404:
            await show(callback, t(locale, "service_error"))
            return
    except ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    else:
        await show_main_menu(callback, state, profile)
        return
    await show_onboarding(callback, state, locale)


@router.callback_query(F.data == "onboard:language")
async def onboarding_language(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    await state.clear()
    await state.update_data(locale=locale)
    await show(
        callback,
        t(locale, "choose_locale"),
        locale_buttons("onboard:locale", locale, "onboard:back", selected=locale),
    )


@router.callback_query(F.data == "onboard:link")
async def existing_account(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    await state.clear()
    await state.update_data(locale=locale)
    await show(callback, t(locale, "link_help"), keyboard([[(t(locale, "back"), "onboard:back")]]))


@router.callback_query(F.data == "onboard:back")
async def onboarding_back(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    await state.clear()
    await show_onboarding(callback, state, locale)


@router.callback_query(F.data == "onboard:create")
async def new_account(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    await state.set_state(Registration.username)
    await state.update_data(locale=locale)
    await show(callback, t(locale, "username_prompt"), keyboard([[(t(locale, "cancel"), "onboard:back")]]))


@router.message(Registration.username)
async def registration_username(message: Message, state: FSMContext) -> None:
    locale = await current_locale(message, state)
    username = (message.text or "").strip()
    if not 1 <= len(username) <= 30:
        await message.answer(t(locale, "username_invalid"))
        return
    await state.update_data(username=username)
    await state.set_state(Registration.learning_language)
    await show(message, t(locale, "learning_prompt"), locale_buttons("reg:learn", locale, "reg:back:name"))


@router.callback_query(F.data == "reg:back:name")
async def registration_back_name(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != Registration.learning_language.state:
        await callback.answer()
        return
    locale = await current_locale(callback, state)
    await state.set_state(Registration.username)
    await show(callback, t(locale, "username_prompt"), keyboard([[(t(locale, "cancel"), "onboard:back")]]))


@router.callback_query(F.data.startswith("reg:learn:"))
async def registration_learning(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != Registration.learning_language.state:
        await callback.answer()
        return
    learning = callback.data.rsplit(":", 1)[-1]
    if learning not in LANGUAGES:
        await callback.answer()
        return
    data = await state.get_data()
    locale = data["locale"]
    await state.update_data(learning_language=learning)
    await state.set_state(Registration.confirmation)
    await show(
        callback,
        t(
            locale,
            "confirm",
            username=escape(data["username"]),
            language=language_name(locale, locale),
            learning=language_name(locale, learning),
        ),
        keyboard(
            [
                [(t(locale, "create"), "reg:create")],
                [(t(locale, "back"), "reg:back:learning"), (t(locale, "cancel"), "onboard:back")],
            ]
        ),
    )


@router.callback_query(F.data == "reg:back:learning")
async def registration_back_learning(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != Registration.confirmation.state:
        await callback.answer()
        return
    locale = await current_locale(callback, state)
    await state.set_state(Registration.learning_language)
    await show(callback, t(locale, "learning_prompt"), locale_buttons("reg:learn", locale, "reg:back:name"))


@router.callback_query(F.data == "reg:create")
async def registration_create(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != Registration.confirmation.state:
        await callback.answer()
        return
    data = await state.get_data()
    locale = data["locale"]
    try:
        profile = await api.register(callback.from_user.id, data["username"], locale, data["learning_language"])
    except ApiError as error:
        if error.detail == "username_already_exists":
            await state.set_state(Registration.username)
            await show(callback, t(locale, "username_taken"), keyboard([[(t(locale, "cancel"), "onboard:back")]]))
        elif error.detail == "telegram_already_linked":
            await state.clear()
            await home(callback, state, api)
        else:
            await show(callback, t(locale, "service_error"))
        return
    except ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_main_menu(callback, state, profile, t(locale, "registered"))
