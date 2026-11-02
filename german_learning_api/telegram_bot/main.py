import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message


async def handle_start(message: Message) -> None:
    await message.answer("Привет! Бот запущен.")


async def main() -> None:
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    dispatcher = Dispatcher()
    dispatcher.message.register(handle_start, CommandStart())
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
