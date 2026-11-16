from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, locale_buttons, reset_navigation_state, show
from telegram_bot.screens.profile import show_account, show_profile
from telegram_bot.states import ProfileEdit
from telegram_bot.texts import LANGUAGES, language_name, t

router = Router()


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_account(callback, state, api)


@router.callback_query(F.data.startswith("profile:edit:"))
async def edit_profile(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    field = callback.data.rsplit(":", 1)[-1]
    if field not in {"locale", "learning", "username", "email", "avatar"}:
        await callback.answer()
        return
    locale = await current_locale(callback, state)
    try:
        profile = await api.profile(callback.from_user.id)
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    locale = profile["current_using_language"]
    await state.update_data(locale=locale)
    if field in ("locale", "learning"):
        current = profile["current_using_language" if field == "locale" else "current_learning_language"]
        await state.set_state(ProfileEdit.locale if field == "locale" else ProfileEdit.learning_language)
        await state.update_data(edit_value=current)
        title = t(
            locale, "edit_locale" if field == "locale" else "edit_learning", current=language_name(locale, current)
        )
        await show(
            callback,
            title,
            locale_buttons(f"profile:set:{field}", locale, "profile:open", selected=current),
        )
    elif field == "username":
        await state.set_state(ProfileEdit.username)
        await show(
            callback,
            t(locale, "name_prompt", current=escape(profile["username"])),
            keyboard([[(t(locale, "back"), "profile:open")]]),
        )
    elif field == "email":
        await state.set_state(ProfileEdit.email)
        email = profile.get("email")
        await state.update_data(edit_value=email)
        rows = []
        if email:
            rows.append([(t(locale, "email_delete"), "profile:email:ask-delete")])
        rows.append([(t(locale, "back"), "profile:open")])
        await show(
            callback,
            t(locale, "email_prompt", current=escape(email) if email else t(locale, "empty")),
            keyboard(rows),
        )
    elif field == "avatar":
        await state.set_state(ProfileEdit.avatar)
        rows = [[(t(locale, "back"), "profile:open")]]
        if profile.get("avatar"):
            rows.insert(0, [(t(locale, "avatar_delete"), "profile:avatar:ask-delete")])
        await show(
            callback,
            t(locale, "avatar_prompt", current=t(locale, "avatar_yes" if profile.get("avatar") else "avatar_no")),
            keyboard(rows),
        )


@router.callback_query(F.data.startswith("profile:set:"))
async def set_profile_language(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    parts = callback.data.split(":", 3)
    if len(parts) != 4:
        await callback.answer()
        return
    _, _, field, language = parts
    if field not in ("locale", "learning") or language not in LANGUAGES:
        await callback.answer()
        return
    locale = await current_locale(callback, state)
    expected = ProfileEdit.locale if field == "locale" else ProfileEdit.learning_language
    if await state.get_state() != expected.state:
        await callback.answer(t(locale, "stale_action"))
        return
    if language == (await state.get_data()).get("edit_value"):
        await callback.answer(t(locale, "already_selected"))
        return
    key = "current_using_language" if field == "locale" else "current_learning_language"
    try:
        profile = await api.update_profile(callback.from_user.id, {key: language})
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, api, t(profile["current_using_language"], "saved"))
