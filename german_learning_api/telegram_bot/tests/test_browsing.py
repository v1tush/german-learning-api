from urllib.parse import parse_qs, urlparse

from telegram_bot.handlers import browse, navigation
from telegram_bot.tests.helpers import BotFlowTests, update


class BrowsingTests(BotFlowTests):
    async def test_support_opens_personal_chat_with_user_id_in_draft(self):
        await navigation.open_support(update(data="support:open"), self.state)

        self.assertIn("Любые вопросы — мы поможем разобраться.", self.show.call_args.args[1])
        contact, menu = (row[0] for row in self.shown_buttons())
        self.assertEqual(contact.text, "✉️ Написать в поддержку")
        self.assertEqual(urlparse(contact.url).path, "/v1tush")
        self.assertIn("ID пользователя: 42", parse_qs(urlparse(contact.url).query)["text"][0])
        self.assertEqual(menu.callback_data, "menu:open")

    async def test_words_sets_and_schedule_open_real_data(self):
        self.api.user_words.return_value = [{"id": 3, "word_id": 5}]
        self.api.word.return_value = {"word": "Haus", "language": "de", "part_of_speech": "noun"}
        self.api.user_word.return_value = {
            "id": 3,
            "word_id": 5,
            "status": "learning",
            "user_hint": "home",
            "translation_selection": {"base_translations": [{"value": "дом"}], "custom_translation": None},
        }

        await browse.open_words(update(data="words:open:0"), self.state, self.api)
        self.assertIn("Мои слова", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:item:3:0:all")
        await browse.open_word_detail(update(data="words:item:3:0:all"), self.state, self.api)
        self.assertIn("Haus", self.show.call_args.args[1])
        self.assertIn("дом", self.show.call_args.args[1])

        self.api.datasets.return_value = [{"id": 9, "name": "Основы"}]
        self.api.dataset.return_value = {"id": 9, "name": "Основы"}
        self.api.dataset_words.return_value = [{"word": "Haus"}]
        await browse.open_datasets(update(data="datasets:open:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:item:9:0:0")
        self.assertEqual(self.shown_buttons()[1][0].callback_data, "datasets:create:0")
        await browse.open_dataset_detail(update(data="datasets:item:9:0:0"), self.state, self.api)
        self.assertIn("Основы", self.show.call_args.args[1])
        self.assertIn("Haus", self.show.call_args.args[1])

        self.api.schedules.return_value = [{"id": 12, "is_enabled": True}]
        self.api.schedule.return_value = {
            "id": 12,
            "is_enabled": True,
            "mode": "interval",
            "exercise_kind": "translation",
            "items_per_delivery": 3,
            "next_run_at": "2026-11-16T12:00:00Z",
        }
        await browse.open_schedules(update(data="schedules:open:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "schedules:item:12:0")
        await browse.open_schedule_detail(update(data="schedules:item:12:0"), self.state, self.api)
        self.assertIn("16.11.2026 12:00 UTC", self.show.call_args.args[1])

    async def test_dataset_pages_keep_the_return_page(self):
        self.api.dataset.return_value = {"id": 9, "name": "Основы"}
        self.api.dataset_words.return_value = [{"word": f"Wort {number}"} for number in range(8)]

        await browse.open_dataset_detail(update(data="datasets:item:9:0:2"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:item:9:1:2")

        await browse.open_dataset_detail(update(data="datasets:item:9:1:2"), self.state, self.api)
        self.assertIn("Wort 7", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:item:9:0:2")
        self.assertEqual(self.shown_buttons()[1][0].callback_data, "datasets:edit:9:1:2")
        self.assertEqual(self.shown_buttons()[2][0].callback_data, "datasets:delete:ask:9:1:2")
        self.assertEqual(self.shown_buttons()[3][0].callback_data, "datasets:open:2")

    async def test_word_detail_shows_only_personal_translations_and_read_only_forms(self):
        self.api.user_word.return_value = {
            "id": 3,
            "word_id": 5,
            "status": "learning",
            "user_hint": None,
            "translation_selection": {
                "base_translations": [
                    {"id": 10, "value": "дом", "is_card_primary": True},
                    {"id": 11, "value": "жилище", "is_card_primary": False},
                ],
                "custom_translation": "здание",
                "custom_is_card_primary": True,
            },
        }
        self.api.word.return_value = {"word": "Haus", "language": "de", "part_of_speech": "noun"}
        self.api.word_inflections.return_value = [{"type": "de_plural", "value": "Häuser"}]

        await browse.open_word_detail(update(data="words:item:3:2:translated"), self.state, self.api)
        body = self.show.call_args.args[1]
        self.assertIn("существительное", body)
        self.assertIn("Häuser", body)
        self.assertIn("⭐ дом", body)
        self.assertIn("• жилище", body)
        self.assertIn("⭐ здание (свой)", body)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:translated:2")

    async def test_translated_filter_includes_custom_only_and_excludes_unselected_words(self):
        self.api.user_words.return_value = [
            {"id": 2, "word_id": 20, "translation_selection": {"base_translations": [], "custom_translation": None}},
            {
                "id": 3,
                "word_id": 30,
                "translation_selection": {"base_translations": [], "custom_translation": "свой перевод"},
            },
        ]
        self.api.word.return_value = {"word": "Haus"}

        await browse.open_translated_words(update(data="words:translated:0"), self.state, self.api)

        self.assertIn("Всего: 1", self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "words:item:3:0:translated")
