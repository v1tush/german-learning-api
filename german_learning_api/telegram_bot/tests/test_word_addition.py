from telegram_bot.api_client import ApiUnavailable
from telegram_bot.handlers import browse, navigation, word_addition, word_primary, word_translations
from telegram_bot.states import WordAddition
from telegram_bot.tests.helpers import BotFlowTests, update, user_profile


class WordAdditionTests(BotFlowTests):
    async def start_flow(self, suggestions=None):
        self.api.profile.side_effect = None
        self.api.profile.return_value = user_profile()
        self.api.create_word.return_value = {"id": 9}
        self.api.word_translations.return_value = {"translations": suggestions or []}
        await word_addition.start_word_addition(update(data="words:add"), self.state, self.api)
        await word_addition.receive_spelling(update(data="  Haus  "), self.state)
        await word_addition.choose_part_of_speech(update(data="words:add:pos:noun"), self.state, self.api)

    async def test_five_shared_and_custom_with_two_primaries_are_saved(self):
        await self.start_flow([{"id": number, "value": f"вариант {number}"} for number in range(1, 7)])
        self.api.create_word.assert_awaited_once_with(42, "Haus", "de", "noun")

        for number in range(1, 6):
            await word_translations.toggle_translation(update(data=f"words:add:translation:{number}:0"), self.state)
        await word_translations.toggle_translation(update(data="words:add:translation:6:0"), self.state)
        self.assertIn("не больше пяти", self.show.call_args.args[1])

        await word_translations.enter_custom_translation(update(data="words:add:custom"), self.state)
        await word_translations.receive_custom_translation(update(data="  жилище  "), self.state)
        self.assertEqual((await self.state.get_data())["custom_translation"], "жилище")
        await word_translations.finish_translation_selection(update(data="words:add:next"), self.state)
        self.assertEqual(await self.state.get_state(), WordAddition.primaries.state)
        self.assertEqual(
            [button.callback_data for row in self.shown_buttons()[:-1] for button in row],
            [*(f"words:add:primary:base:{number}" for number in range(1, 6)), "words:add:primary:custom"],
        )

        await word_primary.toggle_primary(update(data="words:add:primary:base:1"), self.state)
        await word_primary.toggle_primary(update(data="words:add:primary:custom"), self.state)
        await word_primary.toggle_primary(update(data="words:add:primary:base:2"), self.state)
        self.assertIn("не больше двух", self.show.call_args.args[1])
        await word_primary.review_word(update(data="words:add:review"), self.state)

        self.api.add_user_word.return_value = {"id": 17, "word_id": 9}
        self.api.user_word.return_value = {
            "id": 17,
            "word_id": 9,
            "status": "learning",
            "user_hint": None,
            "translation_selection": {
                "base_translations": [{"id": 1, "value": "вариант 1", "is_card_primary": True}],
                "custom_translation": "жилище",
                "custom_is_card_primary": True,
            },
        }
        self.api.word.return_value = {"word": "Haus", "language": "de", "part_of_speech": "noun"}
        await word_primary.save_word(update(data="words:add:save"), self.state, self.api)

        self.api.add_user_word.assert_awaited_once_with(
            42,
            9,
            {
                "base_translation_ids": [1, 2, 3, 4, 5],
                "primary_base_translation_ids": [1],
                "custom_translation": "жилище",
                "custom_is_card_primary": True,
            },
        )
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Слово добавлено", self.show.call_args.args[1])

    async def test_word_without_translation_stays_in_all_words_only(self):
        await self.start_flow()
        await word_translations.without_translation(update(data="words:add:without"), self.state)
        self.api.add_user_word.return_value = {"id": 17, "word_id": 9}
        self.api.user_word.return_value = {
            "id": 17,
            "word_id": 9,
            "status": "learning",
            "user_hint": None,
            "translation_selection": {"base_translations": [], "custom_translation": None},
        }
        self.api.word.return_value = {"word": "Haus", "language": "de", "part_of_speech": "noun"}
        await word_primary.save_word(update(data="words:add:save"), self.state, self.api)
        self.api.add_user_word.assert_awaited_once_with(42, 9, None)

        self.api.user_words.return_value = [{**self.api.user_word.return_value, "id": 17}]
        await browse.open_words(update(data="words:open:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:item:17:0:all")
        await browse.open_translated_words(update(data="words:translated:0"), self.state, self.api)
        self.assertIn("Пока нет слов с выбранным переводом", self.show.call_args.args[1])

    async def test_existing_word_is_opened_without_overwriting_it(self):
        self.api.user_words.return_value = [{"id": 17, "word_id": 9}]
        await self.start_flow()
        self.assertIsNone(await self.state.get_state())
        self.assertIn("уже есть", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:item:17:0:all")
        self.api.add_user_word.assert_not_awaited()

    async def test_unavailable_suggestions_leave_custom_input_and_cancel_available(self):
        await self.start_flow()
        self.api.suggest_translations.side_effect = ApiUnavailable("api_unavailable")
        await word_translations.suggest_translations(update(data="words:add:suggest"), self.state, self.api)
        self.assertIn("Не удалось получить новые переводы", self.show.call_args.args[1])
        await word_translations.enter_custom_translation(update(data="words:add:custom"), self.state)
        await word_translations.receive_custom_translation(update(data="дом"), self.state)
        self.assertEqual(await self.state.get_state(), WordAddition.translations.state)
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertIn("Мои слова", self.show.call_args.args[1])

    async def test_generated_suggestions_can_be_selected_as_primary(self):
        await self.start_flow()
        self.api.suggest_translations.return_value = {
            "status": "success",
            "translations": [{"id": 10, "value": "дом", "is_main": True}],
        }
        await word_translations.suggest_translations(update(data="words:add:suggest"), self.state, self.api)
        self.api.suggest_translations.assert_awaited_once_with(42, 9)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:add:translation:10:0")
        await word_translations.toggle_translation(update(data="words:add:translation:10:0"), self.state)
        await word_translations.finish_translation_selection(update(data="words:add:next"), self.state)
        await word_primary.toggle_primary(update(data="words:add:primary:base:10"), self.state)
        self.assertEqual((await self.state.get_data())["primary_keys"], ["base:10"])
