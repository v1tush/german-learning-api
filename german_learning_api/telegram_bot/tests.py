from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from telegram_bot import main as bot
from telegram_bot.api_client import ApiError
from telegram_bot.texts import locale_from_telegram


def update(language="ru", data=None):
    return SimpleNamespace(from_user=SimpleNamespace(id=42, language_code=language), data=data, text=data)


def profile(language="ru"):
    return {
        "username": "learner",
        "email": None,
        "current_using_language": language,
        "current_learning_language": "de",
        "avatar": None,
    }


class BotFlowTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MemoryStorage()
        self.state = FSMContext(storage=self.storage, key=StorageKey(bot_id=1, chat_id=42, user_id=42))
        self.api = SimpleNamespace(
            profile=AsyncMock(side_effect=ApiError(404, "user_does_not_exist")),
            register=AsyncMock(return_value=profile()),
            confirm_link=AsyncMock(return_value={"user_id": 1, "telegram_id": 42}),
            update_profile=AsyncMock(return_value=profile("de")),
        )
        self.show_patch = patch.object(bot, "show", new_callable=AsyncMock)
        self.show = self.show_patch.start()

    async def asyncTearDown(self):
        self.show_patch.stop()
        await self.storage.close()

    async def test_telegram_locale_normalization_and_unsupported_language_choice(self):
        self.assertEqual(locale_from_telegram("de-DE"), "de")
        self.assertEqual(locale_from_telegram("en_US"), "en")
        self.assertIsNone(locale_from_telegram("fr"))

        await bot.start(update("fr"), SimpleNamespace(args=None), self.state, self.api)

        self.assertIn("Choose your interface language", self.show.call_args.args[1])
        self.assertIsNone((await self.state.get_data()).get("locale"))
        await bot.choose_onboarding_locale(update("fr", "onboard:locale:ru"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["locale"], "ru")
        self.assertIn("У тебя уже есть аккаунт", self.show.call_args.args[1])

    async def test_registration_flow_uses_bot_api_and_clears_fsm(self):
        await bot.start(update(), SimpleNamespace(args=None), self.state, self.api)
        await bot.new_account(update(data="onboard:no"), self.state)
        self.assertEqual(await self.state.get_state(), bot.Registration.username.state)

        await bot.registration_username(update(data="learner"), self.state)
        self.assertEqual(await self.state.get_state(), bot.Registration.learning_language.state)
        await bot.registration_learning(update(data="reg:learn:de"), self.state)
        self.assertEqual(await self.state.get_state(), bot.Registration.confirmation.state)
        await bot.registration_create(update(data="reg:create"), self.state, self.api)

        self.api.register.assert_awaited_once_with(42, "learner", "ru", "de")
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Аккаунт создан", self.show.call_args.args[1])

    async def test_deep_link_confirms_existing_account_and_uses_saved_locale(self):
        self.api.profile.side_effect = None
        self.api.profile.return_value = profile("de")

        await bot.start(update("ru"), SimpleNamespace(args="one-time-token"), self.state, self.api)

        self.api.confirm_link.assert_awaited_once_with(42, "one-time-token")
        self.assertEqual((await self.state.get_data())["locale"], "de")
        self.assertIn("Wozzi-Profil", self.show.call_args.args[1])

    async def test_expired_or_invalid_deep_link_returns_to_onboarding(self):
        self.api.confirm_link.side_effect = ApiError(400, "invalid_or_expired_telegram_link_token")

        await bot.start(update(), SimpleNamespace(args="expired"), self.state, self.api)

        self.assertIn("Ссылка привязки недействительна", self.show.call_args.args[1])
        self.assertIn("У тебя уже есть аккаунт", self.show.call_args.args[1])

    async def test_profile_language_change_calls_patch_and_updates_locale(self):
        await self.state.update_data(locale="ru")

        await bot.set_profile_language(update(data="profile:set:locale:de"), self.state, self.api)

        self.api.update_profile.assert_awaited_once_with(42, {"current_using_language": "de"})
        self.assertEqual((await self.state.get_data())["locale"], "de")
