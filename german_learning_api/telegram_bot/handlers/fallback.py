from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.common import current_locale, keyboard, show
from telegram_bot.texts import t

router = Router()


@router.message()
async def other_message(message: Message, state: FSMContext) -> None:
    locale = await current_locale(message, state)
    if await state.get_state():
        await message.answer(t(locale, "use_buttons"))
        return
    await show(message, t(locale, "unknown_text"), keyboard([[(t(locale, "menu_button"), "menu:open")]]))


@router.callback_query()
async def other_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer(t(await current_locale(callback, state), "stale_action"))
