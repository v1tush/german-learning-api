from telegram_bot.api_client import ApiError, ApiUnavailable
from telegram_bot.handlers import dataset_deletion, dataset_form, navigation
from telegram_bot.states import DatasetDeletion, DatasetForm
from telegram_bot.tests.helpers import BotFlowTests, update
from telegram_bot.texts import TEXTS, t


class DatasetFlowTests(BotFlowTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.api.tags.return_value = [{"id": 9, "name": "Глаголы"}]
        self.api.user_words.return_value = [{"id": 3, "word_id": 5}]
        self.api.word.return_value = {"word": "gehen"}
        self.api.dataset.return_value = {"id": 11, "name": "A1", "tags": [9], "extra_words": [3]}
        self.api.create_dataset.return_value = {"id": 11}
        self.api.update_dataset.return_value = {"id": 11}

    async def test_create_validates_name_and_saves_only_on_confirmation(self):
        await dataset_form.start_dataset_creation(update(data="datasets:create:2"), self.state)
        self.assertEqual(await self.state.get_state(), DatasetForm.name.state)
        await dataset_form.receive_dataset_name(update(data="   "), self.state, self.api)
        self.assertIn(t("ru", "dataset_name_empty"), self.show.call_args.args[1])
        await dataset_form.receive_dataset_name(update(data="x" * 101), self.state, self.api)
        self.assertIn(t("ru", "dataset_name_too_long"), self.show.call_args.args[1])
        self.api.create_dataset.assert_not_awaited()

        await dataset_form.receive_dataset_name(update(data="  A1  "), self.state, self.api)
        self.assertEqual(await self.state.get_state(), DatasetForm.review.state)
        self.assertEqual((await self.state.get_data())["dataset_name"], "A1")
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:form:save")
        self.api.create_dataset.assert_not_awaited()

        await dataset_form.save_dataset(update(data="datasets:form:save"), self.state, self.api)
        self.api.create_dataset.assert_awaited_once_with(42, "A1", [], [])
        self.assertIsNone(await self.state.get_state())
        self.assertIn(t("ru", "dataset_created"), self.show.call_args.args[1])

    async def test_duplicate_name_and_unavailable_service_keep_draft(self):
        await dataset_form.start_dataset_creation(update(data="datasets:create:0"), self.state)
        await dataset_form.receive_dataset_name(update(data="A1"), self.state, self.api)
        self.api.create_dataset.side_effect = ApiError(409, "dataset_already_exists")
        duplicate = update(data="datasets:form:save")
        await dataset_form.save_dataset(duplicate, self.state, self.api)
        duplicate.answer.assert_awaited_once_with(t("ru", "dataset_exists"), show_alert=True)
        self.assertEqual(await self.state.get_state(), DatasetForm.review.state)

        self.api.create_dataset.side_effect = ApiUnavailable("api_unavailable")
        unavailable = update(data="datasets:form:save")
        await dataset_form.save_dataset(unavailable, self.state, self.api)
        unavailable.answer.assert_awaited_once_with(t("ru", "service_error"), show_alert=True)
        self.assertEqual((await self.state.get_data())["dataset_name"], "A1")

    async def test_edit_loads_existing_selection_and_patches_after_save(self):
        await dataset_form.start_dataset_edit(update(data="datasets:edit:11:1:2"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), DatasetForm.review.state)
        data = await self.state.get_data()
        self.assertEqual(data["dataset_tags"], [9])
        self.assertEqual(data["dataset_extra_words"], [3])
        self.assertIn("Глаголы", self.show.call_args.args[1])
        self.assertIn("gehen", self.show.call_args.args[1])
        self.assertIn("автоматически", self.show.call_args.args[1])

        await dataset_form.change_dataset_name(update(data="datasets:form:name"), self.state)
        await dataset_form.receive_dataset_name(update(data="B1"), self.state, self.api)
        await dataset_form.save_dataset(update(data="datasets:form:save"), self.state, self.api)
        self.api.update_dataset.assert_awaited_once_with(42, 11, "B1", [9], [3])
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:open:2")

    async def test_cancel_returns_to_source_without_mutation(self):
        await dataset_form.start_dataset_creation(update(data="datasets:create:2"), self.state)
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(self.shown_buttons()[0][0].callback_data, "datasets:create:0")
        self.api.create_dataset.assert_not_awaited()

        await dataset_form.start_dataset_edit(update(data="datasets:edit:11:1:2"), self.state, self.api)
        await dataset_form.cancel_dataset_form(update(data="datasets:form:cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:open:2")
        self.api.update_dataset.assert_not_awaited()

    async def test_deleted_sources_are_removed_from_draft(self):
        self.api.tags.return_value = []
        self.api.user_words.return_value = []
        await dataset_form.start_dataset_edit(update(data="datasets:edit:11:0:0"), self.state, self.api)
        data = await self.state.get_data()
        self.assertEqual(data["dataset_tags"], [])
        self.assertEqual(data["dataset_extra_words"], [])
        await dataset_form.save_dataset(update(data="datasets:form:save"), self.state, self.api)
        self.api.update_dataset.assert_awaited_once_with(42, 11, "A1", [], [])

    async def test_delete_requires_confirmation_and_handles_scheduled_set(self):
        await dataset_deletion.ask_delete_dataset(update(data="datasets:delete:ask:11:0:2"), self.state, self.api)
        self.assertEqual(await self.state.get_state(), DatasetDeletion.confirmation.state)
        self.assertIn("A1", self.show.call_args.args[1])
        self.api.delete_dataset.assert_not_awaited()
        self.api.delete_dataset.side_effect = ApiError(409, "dataset_in_use")

        await dataset_deletion.delete_dataset(update(data="datasets:delete:confirm"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertIn(t("ru", "dataset_in_use"), self.show.call_args.args[1])
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:open:2")

        stale = update(data="datasets:delete:confirm")
        await dataset_deletion.delete_dataset(stale, self.state, self.api)
        stale.answer.assert_awaited_once_with(t("ru", "stale_action"))
        self.api.delete_dataset.assert_awaited_once_with(42, 11)

        self.api.delete_dataset.side_effect = None
        await dataset_deletion.ask_delete_dataset(update(data="datasets:delete:ask:11:0:2"), self.state, self.api)
        await dataset_deletion.delete_dataset(update(data="datasets:delete:confirm"), self.state, self.api)
        self.assertIn(t("ru", "dataset_deleted"), self.show.call_args.args[1])
        self.assertIsNone(await self.state.get_state())

    async def test_delete_cancel_and_command_return_to_detail(self):
        await dataset_deletion.ask_delete_dataset(update(data="datasets:delete:ask:11:0:2"), self.state, self.api)
        await dataset_deletion.cancel_delete_dataset(update(data="datasets:delete:cancel"), self.state, self.api)
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:open:2")
        self.api.delete_dataset.assert_not_awaited()

        await dataset_deletion.ask_delete_dataset(update(data="datasets:delete:ask:11:0:2"), self.state, self.api)
        await navigation.cancel(update(data="/cancel"), self.state, self.api)
        self.assertIsNone(await self.state.get_state())
        self.assertEqual(self.shown_buttons()[-2][0].callback_data, "datasets:open:2")

    async def test_locales_have_the_same_dataset_keys(self):
        keys = {key for key in TEXTS["ru"] if key.startswith("dataset_")}
        for locale in ("en", "de"):
            self.assertEqual(keys, {key for key in TEXTS[locale] if key.startswith("dataset_")})
