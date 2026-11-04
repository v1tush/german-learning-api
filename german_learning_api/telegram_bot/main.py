import asyncio
from io import BytesIO

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from environs import Env

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.texts import LANGUAGE_NAMES, LANGUAGES, locale_from_telegram, t

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class Registration(StatesGroup):
    username = State()
    learning_language = State()
    confirmation = State()


class ProfileEdit(StatesGroup):
    username = State()
    email = State()
    avatar = State()


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows]
    )


async def show(target: Message | CallbackQuery, text: str, buttons: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
        if target.message is None:
            return
        try:
            await target.message.edit_text(text, reply_markup=buttons)
        except TelegramBadRequest:
            await target.message.answer(text, reply_markup=buttons)
    else:
        await target.answer(text, reply_markup=buttons)


async def current_locale(source: Message | CallbackQuery, state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("locale") or locale_from_telegram(source.from_user.language_code) or "en"


def locale_buttons(prefix: str, locale: str, back: str | None = None) -> InlineKeyboardMarkup:
    rows = [[(LANGUAGE_NAMES[code], f"{prefix}:{code}")] for code in LANGUAGES]
    if back:
        rows.append([(t(locale, "back"), back)])
    return keyboard(rows)


def onboarding_buttons(locale: str) -> InlineKeyboardMarkup:
    return keyboard([[(t(locale, "yes"), "onboard:yes"), (t(locale, "no"), "onboard:no")]])


async def show_onboarding(target: Message | CallbackQuery, state: FSMContext, locale: str, notice: str = "") -> None:
    await state.update_data(locale=locale)
    content = f"{t(locale, 'welcome')}\n\n{t(locale, 'has_account')}"
    if notice:
        content = f"{notice}\n\n{content}"
    await show(target, content, onboarding_buttons(locale))


async def show_profile(target: Message | CallbackQuery, state: FSMContext, profile: dict, notice: str = "") -> None:
    locale = profile.get("current_using_language") or "en"
    await state.update_data(locale=locale)
    body = t(
        locale,
        "profile",
        username=profile["username"],
        email=profile.get("email") or t(locale, "empty"),
        language=LANGUAGE_NAMES.get(locale, locale),
        learning=LANGUAGE_NAMES.get(profile["current_learning_language"], profile["current_learning_language"]),
        avatar=t(locale, "avatar_yes" if profile.get("avatar") else "avatar_no"),
    )
    if notice:
        body = f"{notice}\n\n{body}"
    await show(
        target,
        body,
        keyboard(
            [
                [
                    (t(locale, "edit_username"), "profile:edit:username"),
                    (t(locale, "edit_email"), "profile:edit:email"),
                ],
                [(t(locale, "edit_locale"), "profile:edit:locale")],
                [(t(locale, "edit_learning"), "profile:edit:learning")],
                [(t(locale, "edit_avatar"), "profile:edit:avatar")],
            ]
        ),
    )


async def home(target: Message | CallbackQuery, state: FSMContext, api: WozziApi, notice: str = "") -> None:
    locale = await current_locale(target, state)
    try:
        profile = await api.profile(target.from_user.id)
    except ApiError as error:
        if error.status != 404:
            await show(target, t(locale, "service_error"))
            return
    except ApiUnavailable:
        await show(target, t(locale, "service_error"))
        return
    else:
        await show_profile(target, state, profile, notice)
        return

    telegram_locale = locale_from_telegram(target.from_user.language_code)
    if not telegram_locale and not (await state.get_data()).get("locale"):
        prompt = t(locale, "choose_locale")
        await show(target, f"{notice}\n\n{prompt}" if notice else prompt, locale_buttons("onboard:locale", locale))
        return
    await show_onboarding(target, state, locale, notice)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext, api: WozziApi) -> None:
    await state.clear()
    locale = locale_from_telegram(message.from_user.language_code) or "en"
    if command.args:
        try:
            await api.confirm_link(message.from_user.id, command.args)
        except ApiError as error:
            if error.status in (400, 422):
                notice = t(locale, "link_invalid")
            elif error.status == 409:
                notice = t(locale, "link_taken")
            else:
                await show(message, t(locale, "service_error"))
                return
            await home(message, state, api, notice)
            return
        except ApiUnavailable:
            await show(message, t(locale, "service_error"))
            return
        await home(message, state, api, t(locale, "link_success"))
        return
    await home(message, state, api)


@router.message(Command("menu", "cancel"))
async def menu(message: Message, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(message, state)
    await state.clear()
    await state.update_data(locale=locale)
    await home(message, state, api)


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
        await show_profile(callback, state, profile)
        return
    await show_onboarding(callback, state, locale)


@router.callback_query(F.data == "onboard:yes")
async def existing_account(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(locale, "site"), url="https://wozzi.com")],
            [InlineKeyboardButton(text=t(locale, "back"), callback_data="onboard:back")],
        ]
    )
    await show(callback, t(locale, "link_help"), buttons)


@router.callback_query(F.data == "onboard:back")
async def onboarding_back(callback: CallbackQuery, state: FSMContext) -> None:
    locale = await current_locale(callback, state)
    await state.clear()
    await show_onboarding(callback, state, locale)


@router.callback_query(F.data == "onboard:no")
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
            username=data["username"],
            language=LANGUAGE_NAMES[locale],
            learning=LANGUAGE_NAMES[learning],
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
    await show_profile(callback, state, profile, t(locale, "registered"))


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await state.clear()
    await home(callback, state, api)


@router.callback_query(F.data.startswith("profile:edit:"))
async def edit_profile(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    field = callback.data.rsplit(":", 1)[-1]
    locale = await current_locale(callback, state)
    try:
        profile = await api.profile(callback.from_user.id)
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    locale = profile["current_using_language"]
    await state.update_data(locale=locale)
    if field in ("locale", "learning"):
        title = t(locale, "edit_locale" if field == "locale" else "edit_learning")
        await show(callback, title, locale_buttons(f"profile:set:{field}", locale, "profile:open"))
    elif field == "username":
        await state.set_state(ProfileEdit.username)
        await show(callback, t(locale, "name_prompt"), keyboard([[(t(locale, "cancel"), "profile:open")]]))
    elif field == "email":
        await state.set_state(ProfileEdit.email)
        await show(
            callback,
            t(locale, "email_prompt"),
            keyboard(
                [
                    [(t(locale, "email_delete"), "profile:email:delete")],
                    [(t(locale, "cancel"), "profile:open")],
                ]
            ),
        )
    elif field == "avatar":
        await state.set_state(ProfileEdit.avatar)
        rows = [[(t(locale, "cancel"), "profile:open")]]
        if profile.get("avatar"):
            rows.insert(0, [(t(locale, "avatar_delete"), "profile:avatar:delete")])
        await show(callback, t(locale, "avatar_prompt"), keyboard(rows))
    else:
        await callback.answer()


@router.callback_query(F.data.startswith("profile:set:"))
async def set_profile_language(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, field, language = callback.data.split(":", 3)
    if field not in ("locale", "learning") or language not in LANGUAGES:
        await callback.answer()
        return
    locale = await current_locale(callback, state)
    key = "current_using_language" if field == "locale" else "current_learning_language"
    try:
        profile = await api.update_profile(callback.from_user.id, {key: language})
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, t(profile["current_using_language"], "saved"))


async def save_text_profile(message: Message, state: FSMContext, api: WozziApi, field: str) -> None:
    locale = await current_locale(message, state)
    value = (message.text or "").strip()
    if field == "username" and not 1 <= len(value) <= 30:
        await message.answer(t(locale, "username_invalid"))
        return
    if field == "email" and (not value or len(value) > 254):
        await message.answer(t(locale, "email_invalid"))
        return
    try:
        profile = await api.update_profile(message.from_user.id, {field: value})
    except ApiError as error:
        if error.detail in ("username_already_exists", "email_already_exists", "invalid_email"):
            key = {
                "username_already_exists": "username_taken",
                "email_already_exists": "email_taken",
                "invalid_email": "email_invalid",
            }[error.detail]
            await message.answer(t(locale, key))
        else:
            await message.answer(t(locale, "service_error"))
        return
    except ApiUnavailable:
        await message.answer(t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(message, state, profile, t(locale, "saved"))


@router.message(ProfileEdit.username)
async def change_username(message: Message, state: FSMContext, api: WozziApi) -> None:
    await save_text_profile(message, state, api, "username")


@router.message(ProfileEdit.email)
async def change_email(message: Message, state: FSMContext, api: WozziApi) -> None:
    await save_text_profile(message, state, api, "email")


@router.callback_query(F.data == "profile:email:delete")
async def remove_email(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    try:
        profile = await api.update_profile(callback.from_user.id, {"email": None})
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, t(locale, "saved"))


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
    await show_profile(message, state, profile, t(locale, "avatar_saved"))


@router.callback_query(F.data == "profile:avatar:delete")
async def remove_avatar(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    try:
        profile = await api.delete_avatar(callback.from_user.id)
    except ApiError, ApiUnavailable:
        await show(callback, t(locale, "service_error"))
        return
    await state.clear()
    await show_profile(callback, state, profile, t(locale, "avatar_deleted"))


@router.message()
async def other_message(message: Message, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(message, state)
    await home(message, state, api, t(locale, "unknown_text"))


@router.callback_query()
async def other_callback(callback: CallbackQuery) -> None:
    await callback.answer()


async def main() -> None:
    env = Env()
    env.read_env()
    bot = Bot(token=env.str("TELEGRAM_BOT_TOKEN"))
    storage = RedisStorage.from_url(env.str("WOZZI_FSM_REDIS_URL", default="redis://localhost:6379/1"))
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(router)
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        api = WozziApi(
            env.str("WOZZI_API_BASE_URL", default="http://127.0.0.1:8000/api"),
            env.str("TG_BOT_AUTH_KEY"),
            session,
        )
        try:
            await dispatcher.start_polling(bot, api=api)
        finally:
            await storage.close()
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
