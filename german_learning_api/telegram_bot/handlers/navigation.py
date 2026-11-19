from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, reset_navigation_state, show
from telegram_bot.screens.menu import home, show_support
from telegram_bot.screens.onboarding import show_onboarding
from telegram_bot.screens.profile import show_account
from telegram_bot.screens.tag_membership import show_word_tag_picker
from telegram_bot.screens.tags import show_tag_detail, show_tags
from telegram_bot.screens.words import show_words
from telegram_bot.states import ProfileEdit, Registration, TagCreation, TagDeletion, WordAddition
from telegram_bot.texts import locale_from_telegram, t

router = Router()


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, api: WozziApi) -> None:
    saved_locale = await reset_navigation_state(state)
    locale = saved_locale or locale_from_telegram(message.from_user.language_code) or "en"
    if command.args:
        try:
            await api.confirm_link(message.from_user.id, command.args)
        except ApiError as error:
            if error.status in (400, 422):
                notice_key = "link_invalid"
            elif error.status == 409:
                notice_key = "link_taken"
            else:
                await show(message, t(locale, "service_error"))
                return
            await home(message, state, api, notice_key)
            return
        except ApiUnavailable:
            await show(message, t(locale, "service_error"))
            return
        await home(message, state, api, "link_success")
        return
    await home(message, state, api)


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await home(message, state, api)


@router.message(Command("settings"))
async def settings_command(message: Message, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_account(message, state, api)


@router.message(Command("help"))
async def help_command(message: Message, state: FSMContext) -> None:
    locale = await current_locale(message, state)
    await show(
        message,
        t(locale, "help"),
        keyboard(
            [
                [(t(locale, "support_button"), "support:open")],
                [(t(locale, "main_menu_button"), "menu:open")],
            ]
        ),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, api: WozziApi) -> None:
    active = await state.get_state()
    data = await state.get_data()
    locale = await current_locale(message, state)
    await reset_navigation_state(state)
    if active in {
        item.state for item in (Registration.username, Registration.learning_language, Registration.confirmation)
    }:
        await show_onboarding(message, state, locale)
    elif active in {
        item.state
        for item in (
            ProfileEdit.username,
            ProfileEdit.email,
            ProfileEdit.email_delete_confirmation,
            ProfileEdit.avatar,
            ProfileEdit.avatar_delete_confirmation,
            ProfileEdit.locale,
            ProfileEdit.learning_language,
        )
    }:
        await show_account(message, state, api)
    elif active in {item.state for item in WordAddition.__states__}:
        await show_words(message, state, api, 0)
    elif active == TagCreation.name.state:
        if data.get("tag_origin") == "word":
            await show_word_tag_picker(
                message, state, api, data["tag_user_word_id"], data["tag_word_page"], data["tag_mode"], data["tag_page"]
            )
        else:
            await show_tags(message, state, api, data.get("tag_page", 0))
    elif active == TagDeletion.confirmation.state:
        await show_tag_detail(message, state, api, data["tag_id"], data["tag_detail_page"], data["tag_page"])
    else:
        await home(message, state, api)


@router.callback_query(F.data == "menu:open")
async def open_menu(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await home(callback, state, api)


@router.callback_query(F.data == "support:open")
async def open_support(callback: CallbackQuery, state: FSMContext) -> None:
    await show_support(callback, state)
