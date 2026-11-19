from telegram_bot.api_client import ApiError, ApiUnavailable
from telegram_bot.handlers import navigation, tags
from telegram_bot.states import TagCreation, TagDeletion
from telegram_bot.tests.helpers import BotFlowTests, update


class TagFlowTests(BotFlowTests):
    async def test_list_and_detail_show_tags_and_words(self):
        self.api.tags.return_value = [{"id": 9, "name": "Глаголы"}]
        self.api.tag.return_value = {"id": 9, "name": "Глаголы", "weight": 1}
        self.api.tag_words.return_value = [{"id": 3, "word": "gehen"}]

        await tags.open_tags(update(data="tags:open:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:item:9:0:0")
        await tags.open_tag_detail(update(data="tags:item:9:0:0"), self.state, self.api)
        self.assertIn("Глаголы", self.show.call_args.args[1])
        self.assertIn("gehen", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:pick:9:0:0")

    async def test_create_tag_validates_name_and_keeps_duplicate_form(self):
        await tags.start_create_tag(update(data="tags:create:list:0"), self.state)
        self.assertEqual(await self.state.get_state(), TagCreation.name.state)
        await tags.receive_tag_name(update(data="   "), self.state, self.api)
        self.api.create_tag.assert_not_awaited()
        await tags.receive_tag_name(update(data="x" * 51), self.state, self.api)
        self.api.create_tag.assert_not_awaited()

        self.api.create_tag.side_effect = ApiError(409, "tag_already_exists")
        await tags.receive_tag_name(update(data="Глаголы"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), TagCreation.name.state)
        self.assertIn("уже есть", self.show.call_args.args[1])

        self.api.create_tag.side_effect = None
        self.api.create_tag.return_value = {"id": 9, "name": "Глаголы"}
        self.api.tag.return_value = {"id": 9, "name": "Глаголы"}
        await tags.receive_tag_name(update(data="  Глаголы  "), self.state, self.api)
        self.api.create_tag.assert_awaited_with(42, "Глаголы")
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Тег создан", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:pick:9:0:0")

    async def test_create_from_word_adds_new_tag(self):
        self.api.create_tag.return_value = {"id": 9, "name": "Глаголы"}
        self.api.user_word.return_value = {"id": 3, "word_id": 5, "tags": [9]}
        self.api.word.return_value = {"word": "gehen"}
        self.api.tags.return_value = [{"id": 9, "name": "Глаголы"}]

        await tags.start_create_tag(update(data="tags:create:word:3:2:t:0"), self.state)
        await tags.receive_tag_name(update(data="Глаголы"), self.state, self.api)

        self.api.add_tag_word.assert_awaited_once_with(42, 9, 3)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:wt:r:3:9:2:t:0")
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "words:item:3:2:translated")

    async def test_delete_requires_confirmation_and_stale_button_is_harmless(self):
        self.api.tag.return_value = {"id": 9, "name": "Глаголы"}
        await tags.ask_delete_tag(update(data="tags:delete:ask:9:1:2"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), TagDeletion.confirmation.state)
        self.assertIn("Состав наборов", self.show.call_args.args[1])
        self.api.delete_tag.assert_not_awaited()

        await tags.cancel_delete_tag(update(data="tags:delete:cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        stale = update(data="tags:delete:confirm")
        await tags.delete_tag(stale, self.state, self.api)
        self.api.delete_tag.assert_not_awaited()
        stale.answer.assert_awaited_once()

    async def test_delete_failure_keeps_confirmation_and_success_returns_to_list(self):
        self.api.tag.return_value = {"id": 9, "name": "Глаголы"}
        await tags.ask_delete_tag(update(data="tags:delete:ask:9:0:1"), self.state, self.api)
        self.api.delete_tag.side_effect = ApiUnavailable("api_unavailable")
        failed = update(data="tags:delete:confirm")
        await tags.delete_tag(failed, self.state, self.api)
        self.assertEqual(await self.state.get_state(), TagDeletion.confirmation.state)
        failed.answer.assert_awaited_once_with("Сервис сейчас недоступен. Попробуй позже.", show_alert=True)

        self.api.delete_tag.side_effect = None
        await tags.delete_tag(update(data="tags:delete:confirm"), self.state, self.api)
        self.api.delete_tag.assert_awaited_with(42, 9)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Тег удалён", self.show.call_args.args[1])

    async def test_cancel_command_returns_to_tag_list(self):
        await tags.start_create_tag(update(data="tags:create:list:2"), self.state)
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Мои теги", self.show.call_args.args[1])
