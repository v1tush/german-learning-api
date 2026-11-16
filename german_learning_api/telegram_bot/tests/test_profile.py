from types import SimpleNamespace

from telegram_bot.handlers import fallback, navigation, onboarding, profile_text
from telegram_bot.handlers import profile as profile_handler
from telegram_bot.screens import profile as profile_screen
from telegram_bot.states import ProfileEdit
from telegram_bot.tests.helpers import BotFlowTests, update, user_profile


class ProfileTests(BotFlowTests):
    async def test_profile_language_change_calls_patch_and_updates_locale(self):
        await self.state.set_state(ProfileEdit.locale)
        await self.state.update_data(locale="ru", edit_value="ru")

        await profile_handler.set_profile_language(update(data="profile:set:locale:de"), self.state, self.api)

        self.api.update_profile.assert_awaited_once_with(42, {"current_using_language": "de"})
        self.assertEqual((await self.state.get_data())["locale"], "de")
        self.assertIn("Wähle aus, was du ändern möchtest.", self.show_photo.call_args.args[2])

    async def test_profile_uses_uploaded_avatar_when_available(self):
        from io import BytesIO

        from PIL import Image

        image = BytesIO()
        Image.new("RGB", (40, 40), "red").save(image, format="PNG")
        self.api.avatar.return_value = image.getvalue()
        self.api.profile.side_effect = None
        self.api.profile.return_value = {**user_profile(), "avatar": "users/avatars/7/avatar.png"}

        await profile_handler.open_profile(update(data="profile:open"), self.state, self.api)

        self.api.avatar.assert_awaited_once_with(42)
        self.assertTrue(self.show_photo.call_args.args[1].startswith(b"\xff\xd8"))

        self.assertEqual(self.shown_photo_buttons()[-1][0].callback_data, "menu:open")

    async def test_main_menu_and_account_screen(self):
        self.api.profile.side_effect = None
        self.api.profile.return_value = user_profile()

        await navigation.start(update(), SimpleNamespace(args=None), self.state, self.api)
        self.assertIn("Добро пожаловать в Wozzi", self.show.call_args.args[1])
        self.assertEqual(
            [[button.callback_data for button in row] for row in self.shown_buttons()],
            [
                ["words:open:0", "datasets:open:0"],
                ["schedules:open:0", "profile:open"],
                ["support:open"],
            ],
        )

        await profile_handler.open_profile(update(data="profile:open"), self.state, self.api)
        self.assertIn("Твой профиль", self.show_photo.call_args.args[2])
        self.assertIn("Выбери, что изменить.", self.show_photo.call_args.args[2])
        self.assertTrue(self.show_photo.call_args.args[1].startswith(b"\xff\xd8"))
        self.assertEqual(
            [row[0].callback_data for row in self.shown_photo_buttons()],
            [
                "profile:edit:username",
                "profile:edit:email",
                "profile:edit:locale",
                "profile:edit:learning",
                "profile:edit:avatar",
                "menu:open",
            ],
        )
        self.assertIn("Немецкий", self.shown_photo_buttons()[3][0].text)

    async def test_cancel_returns_to_current_section_and_menu_returns_to_main_screen(self):
        await navigation.start(update(), SimpleNamespace(args=None), self.state, self.api)
        await onboarding.new_account(update(data="onboard:create"), self.state)
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Добро пожаловать", self.show.call_args.args[1])

        self.api.profile.side_effect = None
        self.api.profile.return_value = user_profile()
        await profile_handler.edit_profile(update(data="profile:edit:username"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), ProfileEdit.username.state)
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "profile:open")
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Выбери, что изменить.", self.show_photo.call_args.args[2])

        await navigation.menu(update(data="/menu"), self.state, self.api)
        self.assertIn("Добро пожаловать в Wozzi", self.show.call_args.args[1])

    async def test_email_delete_requires_confirmation(self):
        self.api.profile.side_effect = None
        self.api.profile.return_value = {**user_profile(), "email": "old@example.com"}
        self.api.update_profile.return_value = user_profile()

        await profile_handler.edit_profile(update(data="profile:edit:email"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), ProfileEdit.email.state)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "profile:email:ask-delete")

        await profile_text.ask_remove_email(update(data="profile:email:ask-delete"), self.state)
        self.assertEqual(await self.state.get_state(), ProfileEdit.email_delete_confirmation.state)
        self.assertIn("old@example.com", self.show.call_args.args[1])

        await profile_text.remove_email(update(data="profile:email:delete"), self.state, self.api)
        self.api.update_profile.assert_awaited_once_with(42, {"email": None})
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Выбери, что изменить.", self.show_photo.call_args.args[2])
        self.assertEqual(self.shown_photo_buttons()[-1][0].callback_data, "menu:open")

    async def test_stale_delete_button_cannot_delete_email(self):
        callback = update(data="profile:email:delete")
        await profile_text.remove_email(callback, self.state, self.api)
        callback.answer.assert_awaited_once()
        self.api.update_profile.assert_not_awaited()

    async def test_user_text_is_escaped_in_html_and_unknown_input_does_not_reload_profile(self):
        await profile_screen.show_profile(update(), self.state, {**user_profile(), "username": "<Ada & Bob>"}, self.api)
        self.assertIn("&lt;Ada &amp; Bob&gt;", self.show_photo.call_args.args[2])

        self.api.profile.reset_mock()
        await fallback.other_message(update(data="hello"), self.state)
        self.api.profile.assert_not_awaited()
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "menu:open")

        await self.state.set_state(ProfileEdit.learning_language)
        message = update(data="German")
        await fallback.other_message(message, self.state)
        message.answer.assert_awaited_once()
        self.assertIn("/cancel", message.answer.call_args.args[0])
