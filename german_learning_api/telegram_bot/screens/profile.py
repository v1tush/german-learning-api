from html import escape
from io import BytesIO

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, short_button_value, show, show_photo
from telegram_bot.screens.menu import home
from telegram_bot.texts import language_name, t


def placeholder_avatar(username: str) -> bytes:
    image = Image.new("RGB", (400, 400), "#1c3348")
    draw = ImageDraw.Draw(image)
    draw.ellipse((24, 24, 376, 376), fill="#284e70")
    font = ImageFont.load_default(size=180)
    initial = (username.strip()[:1] or "W").upper()
    bounds = draw.textbbox((0, 0), initial, font=font)
    position = ((400 - (bounds[2] - bounds[0])) / 2 - bounds[0], (400 - (bounds[3] - bounds[1])) / 2 - bounds[1])
    draw.text(position, initial, fill="white", font=font)
    result = BytesIO()
    image.save(result, format="JPEG", quality=90)
    return result.getvalue()


async def profile_avatar(api: WozziApi, telegram_id: int, profile: dict) -> bytes:
    if profile.get("avatar"):
        try:
            avatar = await api.avatar(telegram_id)
            if avatar:
                with Image.open(BytesIO(avatar)) as image:
                    output = BytesIO()
                    image.convert("RGB").save(output, format="JPEG", quality=90)
                    return output.getvalue()
        except ApiError, ApiUnavailable, UnidentifiedImageError, OSError:
            pass
    return placeholder_avatar(profile["username"])


async def show_profile(
    target: Message | CallbackQuery, state: FSMContext, profile: dict, api: WozziApi, notice: str = ""
) -> None:
    locale = profile.get("current_using_language") or "en"
    await state.clear()
    await state.update_data(locale=locale)
    body = t(
        locale,
        "profile",
        username=escape(profile["username"]),
        email=escape(profile.get("email") or t(locale, "empty")),
        learning=language_name(locale, profile["current_learning_language"]),
        user_id=str(profile.get("id", target.from_user.id)),
    )
    if notice:
        body = f"{body}\n\n{notice}"
    body = f"{body}\n\n{t(locale, 'choose_change')}"
    await show_photo(
        target,
        await profile_avatar(api, target.from_user.id, profile),
        body,
        profile_buttons(locale, profile),
    )


def profile_buttons(locale: str, profile: dict) -> InlineKeyboardMarkup:
    email = profile.get("email") or t(locale, "empty")
    return keyboard(
        [
            [(t(locale, "settings_username", value=short_button_value(profile["username"])), "profile:edit:username")],
            [(t(locale, "settings_email", value=short_button_value(email)), "profile:edit:email")],
            [(t(locale, "settings_locale", value=language_name(locale, locale)), "profile:edit:locale")],
            [
                (
                    t(locale, "settings_learning", value=language_name(locale, profile["current_learning_language"])),
                    "profile:edit:learning",
                )
            ],
            [
                (
                    t(
                        locale,
                        "settings_avatar",
                        value=t(locale, "avatar_yes" if profile.get("avatar") else "avatar_no"),
                    ),
                    "profile:edit:avatar",
                )
            ],
            [(t(locale, "main_menu_button"), "menu:open")],
        ]
    )


async def show_account(target: Message | CallbackQuery, state: FSMContext, api: WozziApi, notice: str = "") -> None:
    locale = await current_locale(target, state)
    try:
        profile = await api.profile(target.from_user.id)
    except ApiError as error:
        if error.status == 404:
            await home(target, state, api)
            return
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "menu_button"), "menu:open")]]))
        return
    except ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "menu_button"), "menu:open")]]))
        return
    await show_profile(target, state, profile, api, notice)
