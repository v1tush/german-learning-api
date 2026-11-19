import asyncio

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.storage.redis import RedisStorage
from environs import Env

from telegram_bot.api_client import WozziApi
from telegram_bot.common import bot_commands
from telegram_bot.handlers import (
    browse,
    fallback,
    navigation,
    onboarding,
    profile,
    profile_avatar,
    profile_text,
    tag_membership,
    tags,
    word_addition,
    word_deletion,
    word_primary,
    word_translations,
)
from telegram_bot.texts import LANGUAGES


async def main() -> None:
    env = Env()
    env.read_env()
    bot = Bot(token=env.str("TELEGRAM_BOT_TOKEN"))
    storage = RedisStorage.from_url(env.str("WOZZI_FSM_REDIS_URL", default="redis://localhost:6379/1"))
    dispatcher = Dispatcher(storage=storage)
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.callback_query.filter(F.message.chat.type == "private")
    for module in (
        navigation,
        browse,
        onboarding,
        profile,
        profile_text,
        profile_avatar,
        tags,
        tag_membership,
        word_addition,
        word_deletion,
        word_translations,
        word_primary,
        fallback,
    ):
        router.include_router(module.router)
    dispatcher.include_router(router)
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        api = WozziApi(
            env.str("WOZZI_API_BASE_URL", default="http://127.0.0.1:8000/api"),
            env.str("TG_BOT_AUTH_KEY"),
            session,
        )
        try:
            await bot.set_my_commands(bot_commands("en"))
            for locale in LANGUAGES:
                await bot.set_my_commands(bot_commands(locale), language_code=locale)
            await dispatcher.start_polling(bot, api=api)
        finally:
            await storage.close()
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
