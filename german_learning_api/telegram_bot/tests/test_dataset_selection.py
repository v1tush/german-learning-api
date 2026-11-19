from telegram_bot.handlers import dataset_form, dataset_selection
from telegram_bot.states import DatasetForm
from telegram_bot.tests.helpers import BotFlowTests, update


class DatasetSelectionTests(BotFlowTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.api.tags.return_value = [{"id": number, "name": f"Tag {number}"} for number in range(1, 9)]
        self.api.user_words.return_value = [{"id": number, "word_id": number + 100} for number in range(1, 9)]
        self.api.word.return_value = {"word": "gehen"}
        await dataset_form.start_dataset_creation(update(data="datasets:create:0"), self.state)
        await dataset_form.receive_dataset_name(update(data="A1"), self.state, self.api)

    async def test_tag_selection_is_paginated_and_staged_until_save(self):
        await dataset_selection.open_dataset_tags(update(data="datasets:form:tags:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:form:tag:1:0")
        self.assertEqual(self.shown_buttons()[7][0].callback_data, "datasets:form:tags:1")

        await dataset_selection.toggle_dataset_tag(update(data="datasets:form:tag:1:0"), self.state, self.api)
        self.assertIn("✓", self.shown_buttons()[0][0].text)
        self.assertEqual((await self.state.get_data())["dataset_tags"], [1])
        await dataset_selection.open_dataset_tags(update(data="datasets:form:tags:1"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:form:tag:8:1")
        await dataset_selection.toggle_dataset_tag(update(data="datasets:form:tag:8:1"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["dataset_tags"], [1, 8])
        self.api.create_dataset.assert_not_awaited()

        await dataset_selection.toggle_dataset_tag(update(data="datasets:form:tag:1:0"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["dataset_tags"], [8])
        self.assertEqual(await self.state.get_state(), DatasetForm.review.state)

    async def test_word_picker_uses_user_word_ids_and_stages_selection(self):
        await dataset_selection.open_dataset_words(update(data="datasets:form:words:0"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:form:word:8:0")
        self.assertEqual(self.shown_buttons()[7][0].callback_data, "datasets:form:words:1")
        await dataset_selection.toggle_dataset_word(update(data="datasets:form:word:8:0"), self.state, self.api)
        self.assertIn("✓", self.shown_buttons()[0][0].text)
        self.assertEqual((await self.state.get_data())["dataset_extra_words"], [8])
        self.api.update_dataset.assert_not_awaited()
        self.api.create_dataset.assert_not_awaited()

        await dataset_selection.open_dataset_words(update(data="datasets:form:words:1"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:form:word:1:1")
        await dataset_selection.toggle_dataset_word(update(data="datasets:form:word:1:1"), self.state, self.api)
        self.assertEqual((await self.state.get_data())["dataset_extra_words"], [1, 8])

        await dataset_form.review_dataset(update(data="datasets:form:review"), self.state, self.api)
        self.assertIn("Отдельные слова (2)", self.show.call_args.args[1])
        self.api.create_dataset.return_value = {"id": 11}
        self.api.dataset.return_value = {"id": 11, "name": "A1", "tags": [], "extra_words": [1, 8]}
        await dataset_form.save_dataset(update(data="datasets:form:save"), self.state, self.api)
        self.api.create_dataset.assert_awaited_once_with(42, "A1", [], [1, 8])

    async def test_stale_selector_button_does_not_change_form(self):
        await dataset_form.cancel_dataset_form(update(data="datasets:form:cancel"), self.state, self.api)
        stale = update(data="datasets:form:tag:1:0")
        await dataset_selection.toggle_dataset_tag(stale, self.state, self.api)
        stale.answer.assert_awaited_once()
        self.assertNotIn("dataset_tags", await self.state.get_data())
