from html import escape
from urllib.parse import quote

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, locale_buttons, reset_navigation_state, show
from telegram_bot.screens.onboarding import show_onboarding
from telegram_bot.texts import locale_from_telegram, t


def main_menu_buttons(locale: str) -> InlineKeyboardMarkup:
    return keyboard(
        [
            [(t(locale, "words_button"), "words:open:0"), (t(locale, "datasets_button"), "datasets:open:0")],
            [(t(locale, "schedules_button"), "schedules:open:0"), (t(locale, "account_button"), "profile:open")],
            [(t(locale, "support_button"), "support:open")],
        ]
    )


async def show_main_menu(target: Message | CallbackQuery, state: FSMContext, profile: dict, notice: str = "") -> None:
    locale = profile.get("current_using_language") or "en"
    await state.clear()
    await state.update_data(locale=locale)
    body = t(locale, "main_menu", username=escape(profile["username"]))
    if notice:
        body = f"{notice}\n\n{body}"
    await show(target, body, main_menu_buttons(locale))


def support_buttons(locale: str, telegram_id: int) -> InlineKeyboardMarkup:
    draft = t(locale, "support_draft", user_id=str(telegram_id))
    url = f"https://t.me/v1tush?text={quote(draft, safe='')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, "contact_support"), url=url)],
            [InlineKeyboardButton(text=t(locale, "main_menu_button"), callback_data="menu:open")],
        ]
    )


async def show_support(target: Message | CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(target, state)
    await reset_navigation_state(state)
    await show(target, t(locale, "support"), support_buttons(locale, target.from_user.id))


async def home(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, notice_key: str | None = None
) -> None:
    locale = await current_locale(target, state)
    try:
        profile = await api.profile(target.from_user.id)
    except ApiError as error:
        if error.status != 404:
            await show(target, t(locale, "service_error"), keyboard([[(t(locale, "menu_button"), "menu:open")]]))
            return
    except ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "menu_button"), "menu:open")]]))
        return
    else:
        profile_locale = profile.get("current_using_language") or "en"
        await show_main_menu(target, state, profile, t(profile_locale, notice_key) if notice_key else "")
        return

    notice = t(locale, notice_key) if notice_key else ""
    telegram_locale = locale_from_telegram(target.from_user.language_code)
    if not telegram_locale and not (await state.get_data()).get("locale"):
        prompt = t(locale, "choose_locale")
        await show(target, f"{notice}\n\n{prompt}" if notice else prompt, locale_buttons("onboard:locale", locale))
        return
    await show_onboarding(target, state, locale, notice)
