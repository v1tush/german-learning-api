from telegram_bot.api_client import ApiUnavailable
from telegram_bot.handlers import browse, tag_membership
from telegram_bot.tests.helpers import BotFlowTests, update


class TagMembershipTests(BotFlowTests):
    async def test_word_detail_shows_its_tags_and_opens_tag_editor(self):
        self.api.user_word.return_value = {
            "id": 3,
            "word_id": 5,
            "tags": [9],
            "status": "learning",
            "user_hint": None,
            "translation_selection": {"base_translations": [], "custom_translation": None},
        }
        self.api.word.return_value = {"word": "gehen", "language": "de", "part_of_speech": "verb"}
        self.api.tags.return_value = [{"id": 9, "name": "A&B"}]

        await browse.open_word_detail(update(data="words:item:3:2:all"), self.state, self.api)

        self.assertIn("Теги: A&amp;B", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[2][0].callback_data, "tags:word:3:2:a:0")

    async def test_tag_can_add_and_remove_word(self):
        self.api.tag.return_value = {"id": 9, "name": "Глаголы"}
        self.api.user_words.return_value = [{"id": 3, "word_id": 5}]
        self.api.word.return_value = {"word": "gehen"}

        await tag_membership.open_tag_word_picker(update(data="tags:pick:9:0:2"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:tw:a:9:3:0:2")
        self.api.tag_words.return_value = [{"id": 3, "word": "gehen"}]
        await tag_membership.change_tag_word(update(data="tags:tw:a:9:3:0:2"), self.state, self.api)
        self.api.add_tag_word.assert_awaited_once_with(42, 9, 3)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:tw:r:9:3:0:2")
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "tags:item:9:0:2")

        self.api.tag_words.return_value = []
        await tag_membership.change_tag_word(update(data="tags:tw:r:9:3:0:2"), self.state, self.api)
        self.api.remove_tag_word.assert_awaited_once_with(42, 9, 3)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:tw:a:9:3:0:2")

    async def test_word_can_add_and_remove_tag_and_preserves_word_filter(self):
        self.api.user_word.return_value = {"id": 3, "word_id": 5, "tags": []}
        self.api.word.return_value = {"word": "gehen"}
        self.api.tags.return_value = [{"id": 9, "name": "Глаголы"}]

        await tag_membership.open_word_tag_picker(update(data="tags:word:3:2:t:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:wt:a:3:9:2:t:0")
        self.api.user_word.return_value["tags"] = [9]
        await tag_membership.change_word_tag(update(data="tags:wt:a:3:9:2:t:0"), self.state, self.api)
        self.api.add_tag_word.assert_awaited_once_with(42, 9, 3)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:wt:r:3:9:2:t:0")
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "words:item:3:2:translated")

        self.api.user_word.return_value["tags"] = []
        await tag_membership.change_word_tag(update(data="tags:wt:r:3:9:2:t:0"), self.state, self.api)
        self.api.remove_tag_word.assert_awaited_once_with(42, 9, 3)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:wt:a:3:9:2:t:0")

    async def test_api_failure_keeps_selection_available(self):
        self.api.add_tag_word.side_effect = ApiUnavailable("api_unavailable")
        failed = update(data="tags:tw:a:9:3:0:0")

        await tag_membership.change_tag_word(failed, self.state, self.api)

        failed.answer.assert_awaited_once_with("Сервис сейчас недоступен. Попробуй позже.", show_alert=True)
        self.show.assert_not_awaited()

    async def test_picker_pages_preserve_return_context(self):
        self.api.tag.return_value = {"id": 9, "name": "Глаголы"}
        self.api.user_words.return_value = [{"id": number, "word_id": number} for number in range(1, 9)]
        self.api.word.return_value = {"word": "gehen"}

        await tag_membership.open_tag_word_picker(update(data="tags:pick:9:0:2"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[7][0].callback_data, "tags:pick:9:1:2")

        await tag_membership.open_tag_word_picker(update(data="tags:pick:9:1:2"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "tags:tw:a:9:1:1:2")
        self.assertEqual(self.shown_buttons()[1][0].callback_data, "tags:pick:9:0:2")
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "tags:item:9:0:2")

        self.api.user_word.return_value = {"id": 3, "word_id": 5, "tags": []}
        self.api.tags.return_value = [{"id": number, "name": f"Tag {number}"} for number in range(1, 9)]
        await tag_membership.open_word_tag_picker(update(data="tags:word:3:2:t:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[7][0].callback_data, "tags:word:3:2:t:1")
        await tag_membership.open_word_tag_picker(update(data="tags:word:3:2:t:1"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[-1][0].callback_data, "words:item:3:2:translated")
