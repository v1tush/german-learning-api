from html import escape

from aiogram.enums import ButtonStyle
from aiogram.types import CallbackQuery, Message

from telegram_bot.common import keyboard, show
from telegram_bot.texts import t


async def show_delete_confirmation(target: Message | CallbackQuery, locale: str, word: str) -> None:
    await show(
        target,
        t(locale, "word_delete_confirm", word=escape(word)),
        keyboard(
            [
                [(t(locale, "word_delete"), "words:delete:confirm", ButtonStyle.DANGER)],
                [(t(locale, "back"), "words:delete:cancel")],
            ]
        ),
    )
