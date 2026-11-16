from telegram_bot.api_client import ApiUnavailable
from telegram_bot.handlers import browse, word_deletion
from telegram_bot.states import WordDeletion
from telegram_bot.tests.helpers import BotFlowTests, update


class WordDeletionTests(BotFlowTests):
    async def open_word(self):
        self.api.user_word.return_value = {
            "id": 3,
            "word_id": 5,
            "status": "learning",
            "user_hint": None,
            "translation_selection": {"base_translations": [], "custom_translation": None},
        }
        self.api.word.return_value = {"word": "Haus", "language": "de", "part_of_speech": "noun"}
        await browse.open_word_detail(update(data="words:item:3:2:translated"), self.state, self.api)

    async def test_delete_requires_confirmation_and_returns_to_same_filter(self):
        await self.open_word()
        delete_button = self.shown_buttons()[1][0]
        self.assertEqual(delete_button.callback_data, "words:delete:ask:3:2:translated")
        self.assertEqual(delete_button.style, "danger")

        await word_deletion.ask_delete_word(update(data=delete_button.callback_data), self.state, self.api)
        self.assertEqual(await self.state.get_state(), WordDeletion.confirmation.state)
        self.api.delete_user_word.assert_not_awaited()
        self.assertIn("Haus", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:delete:confirm")

        self.api.user_words.return_value = []
        await word_deletion.delete_word(update(data="words:delete:confirm"), self.state, self.api)

        self.api.delete_user_word.assert_awaited_once_with(42, 3)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Слово удалено", self.show.call_args.args[1])
        self.assertIn("Пока нет слов с выбранным переводом", self.show.call_args.args[1])

    async def test_cancel_makes_old_confirmation_button_stale(self):
        await self.open_word()
        await word_deletion.ask_delete_word(update(data="words:delete:ask:3:2:translated"), self.state, self.api)
        await word_deletion.cancel_delete_word(update(data="words:delete:cancel"), self.state, self.api)

        self.assertIsNone(await self.state.get_state())
        self.assertIn("Haus", self.show.call_args.args[1])
        stale = update(data="words:delete:confirm")
        await word_deletion.delete_word(stale, self.state, self.api)
        stale.answer.assert_awaited_once()
        self.api.delete_user_word.assert_not_awaited()

    async def test_api_failure_keeps_confirmation_for_retry(self):
        await self.open_word()
        await word_deletion.ask_delete_word(update(data="words:delete:ask:3:2:translated"), self.state, self.api)
        self.api.delete_user_word.side_effect = ApiUnavailable("api_unavailable")

        failed = update(data="words:delete:confirm")
        await word_deletion.delete_word(failed, self.state, self.api)

        self.assertEqual(await self.state.get_state(), WordDeletion.confirmation.state)
        failed.answer.assert_awaited_once_with("Сервис сейчас недоступен. Попробуй позже.", show_alert=True)
