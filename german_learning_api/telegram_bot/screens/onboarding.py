from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from telegram_bot.common import keyboard, show
from telegram_bot.texts import t


def onboarding_buttons(locale: str) -> InlineKeyboardMarkup:
    return keyboard(
        [
            [(t(locale, "create_account"), "onboard:create"), (t(locale, "link_account"), "onboard:link")],
            [
                (t(locale, "interface_language_button"), "onboard:language"),
                (t(locale, "support_button"), "support:open"),
            ],
        ]
    )


async def show_onboarding(target: Message | CallbackQuery, state: FSMContext, locale: str, notice: str = "") -> None:
    await state.clear()
    await state.update_data(locale=locale)
    content = t(locale, "welcome")
    if notice:
        content = f"{notice}\n\n{content}"
    await show(target, content, onboarding_buttons(locale))
