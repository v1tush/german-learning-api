from types import SimpleNamespace

from telegram_bot.api_client import ApiError
from telegram_bot.common import bot_commands
from telegram_bot.handlers import navigation, onboarding
from telegram_bot.states import Registration
from telegram_bot.tests.helpers import BotFlowTests, update, user_profile
from telegram_bot.texts import locale_from_telegram


class OnboardingTests(BotFlowTests):
    async def test_telegram_locale_normalization_and_unsupported_language_choice(self):
        self.assertEqual(locale_from_telegram("de-DE"), "de")
        self.assertEqual(locale_from_telegram("en_US"), "en")
        self.assertIsNone(locale_from_telegram("fr"))

        await navigation.start(update("fr"), SimpleNamespace(args=None), self.state, self.api)

        self.assertIn("Interface language", self.show.call_args.args[1])
        self.assertIsNone((await self.state.get_data()).get("locale"))
        await navigation.menu(update("fr", "/menu"), self.state, self.api)
        self.assertIn("Interface language", self.show.call_args.args[1])
        await onboarding.choose_onboarding_locale(update("fr", "onboard:locale:ru"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["locale"], "ru")
        self.assertIn("Добро пожаловать", self.show.call_args.args[1])

    async def test_onboarding_actions_and_language_switch(self):
        await navigation.start(update(), SimpleNamespace(args=None), self.state, self.api)

        self.assertEqual(
            [[button.callback_data for button in row] for row in self.shown_buttons()],
            [["onboard:create", "onboard:link"], ["onboard:language", "support:open"]],
        )

        await onboarding.onboarding_language(update(data="onboard:language"), self.state)
        self.assertIn("Язык интерфейса", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].text, "✓ Русский")

        await onboarding.choose_onboarding_locale(update(data="onboard:locale:de"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["locale"], "de")
        self.assertIn("Willkommen bei Wozzi", self.show.call_args.args[1])

        await navigation.start(update("ru"), SimpleNamespace(args=None), self.state, self.api)
        self.assertIn("Willkommen bei Wozzi", self.show.call_args.args[1])

        await onboarding.existing_account(update(data="onboard:link"), self.state)
        self.assertEqual([row[0].callback_data for row in self.shown_buttons()], ["onboard:back"])
        self.assertIn("Website", self.show.call_args.args[1])

    async def test_help_and_settings_commands_are_available(self):
        self.assertEqual(
            [command.command for command in bot_commands("ru")],
            ["start", "menu", "settings", "help", "cancel"],
        )
        self.assertEqual(bot_commands("de")[2].description, "Profileinstellungen")

        await navigation.help_command(update(data="/help"), self.state)
        self.assertIn("Как пользоваться Wozzi", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "support:open")
        self.assertEqual(self.shown_buttons()[1][0].callback_data, "menu:open")

        await navigation.settings_command(update(data="/settings"), self.state, self.api)
        self.assertIn("Добро пожаловать", self.show.call_args.args[1])

    async def test_registration_flow_uses_bot_api_and_clears_fsm(self):
        await navigation.start(update(), SimpleNamespace(args=None), self.state, self.api)
        await onboarding.new_account(update(data="onboard:create"), self.state)
        self.assertEqual(await self.state.get_state(), Registration.username.state)

        await onboarding.registration_username(update(data="learner"), self.state)
        self.assertEqual(await self.state.get_state(), Registration.learning_language.state)
        await onboarding.registration_learning(update(data="reg:learn:de"), self.state)
        self.assertEqual(await self.state.get_state(), Registration.confirmation.state)
        await onboarding.registration_create(update(data="reg:create"), self.state, self.api)

        self.api.register.assert_awaited_once_with(42, "learner", "ru", "de")
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Аккаунт создан", self.show.call_args.args[1])

    async def test_deep_link_confirms_existing_account_and_uses_saved_locale(self):
        self.api.profile.side_effect = None
        self.api.profile.return_value = user_profile("de")

        await navigation.start(update("ru"), SimpleNamespace(args="one-time-token"), self.state, self.api)

        self.api.confirm_link.assert_awaited_once_with(42, "one-time-token")
        self.assertEqual((await self.state.get_data())["locale"], "de")
        self.assertIn("Dein Konto ist mit Telegram verknüpft", self.show.call_args.args[1])
        self.assertIn("Willkommen bei Wozzi", self.show.call_args.args[1])

    async def test_expired_or_invalid_deep_link_returns_to_onboarding(self):
        self.api.confirm_link.side_effect = ApiError(400, "invalid_or_expired_telegram_link_token")

        await navigation.start(update(), SimpleNamespace(args="expired"), self.state, self.api)

        self.assertIn("Ссылка привязки недействительна", self.show.call_args.args[1])
        self.assertIn("Добро пожаловать", self.show.call_args.args[1])
