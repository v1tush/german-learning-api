from aiogram.enums import ButtonStyle, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from telegram_bot.texts import LANGUAGE_NAMES, LANGUAGES, locale_from_telegram, t

ButtonSpec = tuple[str, str] | tuple[str, str, ButtonStyle]


def keyboard(rows: list[list[ButtonSpec]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button[0],
                    callback_data=button[1],
                    style=button[2] if len(button) == 3 else None,
                )
                for button in row
            ]
            for row in rows
        ]
    )


def bot_commands(locale: str) -> list[BotCommand]:
    return [
        BotCommand(command=command, description=t(locale, f"command_{command}"))
        for command in ("start", "menu", "settings", "help", "cancel")
    ]


async def show(target: Message | CallbackQuery, text: str, buttons: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
        if not isinstance(target.message, Message):
            return
        if target.message.photo:
            await target.message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
            try:
                await target.message.delete()
            except TelegramBadRequest:
                pass
            return
        try:
            await target.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).lower():
                await target.message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    else:
        await target.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)


async def show_photo(
    target: Message | CallbackQuery, photo: bytes, caption: str, buttons: InlineKeyboardMarkup
) -> None:
    image = BufferedInputFile(photo, filename="profile.jpg")
    if isinstance(target, CallbackQuery):
        await target.answer()
        if not isinstance(target.message, Message):
            return
        await target.message.answer_photo(image, caption=caption, reply_markup=buttons, parse_mode=ParseMode.HTML)
        try:
            await target.message.delete()
        except TelegramBadRequest:
            pass
    else:
        await target.answer_photo(image, caption=caption, reply_markup=buttons, parse_mode=ParseMode.HTML)


async def current_locale(source: Message | CallbackQuery, state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("locale") or locale_from_telegram(source.from_user.language_code) or "en"


async def reset_navigation_state(state: FSMContext) -> str | None:
    locale = (await state.get_data()).get("locale")
    await state.clear()
    if locale in LANGUAGES:
        await state.update_data(locale=locale)
        return locale
    return None


def locale_buttons(
    prefix: str, locale: str, back: str | None = None, selected: str | None = None
) -> InlineKeyboardMarkup:
    rows = [[(f"{'✓ ' if code == selected else ''}{LANGUAGE_NAMES[code]}", f"{prefix}:{code}")] for code in LANGUAGES]
    if back:
        rows.append([(t(locale, "back"), back)])
    return keyboard(rows)


def short_button_value(value: str, max_length: int = 24) -> str:
    return value if len(value) <= max_length else f"{value[: max_length - 1]}…"


PAGE_SIZE = 7


def page_of(items: list[dict], requested: int) -> tuple[list[dict], int, int]:
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(0, requested), pages - 1)
    return items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE], page, pages


def page_navigation(prefix: str, page: int, pages: int) -> list[list[tuple[str, str]]]:
    row = []
    if page > 0:
        row.append(("◀️", f"{prefix}:{page - 1}"))
    if page + 1 < pages:
        row.append(("▶️", f"{prefix}:{page + 1}"))
    return [row] if row else []
