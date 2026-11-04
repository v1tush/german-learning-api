from datasets.models import UserDataset as CurrentUserDataset
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word


class StudyScheduleDatasetMigrationTests(TransactionTestCase):
    migrate_from = ("schedules", "0004_remove_schedulerun_delivery_format_and_more")
    migrate_to = ("schedules", "0005_studyschedule_dataset")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_backfill_preserves_tagged_and_all_word_schedules_and_can_reverse(self):
        User = self.old_apps.get_model("users", "User")
        UserTag = self.old_apps.get_model("tags", "UserTag")
        StudySchedule = self.old_apps.get_model("schedules", "StudySchedule")

        user = User.objects.create(username="migration-user", password="unused")
        tag = UserTag.objects.create(user_id=user.pk, name="Animals")
        tagged_schedule = StudySchedule.objects.create(
            user_id=user.pk,
            mode="interval",
            interval_minutes=60,
        )
        tagged_schedule.tags.add(tag)
        all_words_schedule = StudySchedule.objects.create(
            user_id=user.pk,
            mode="interval",
            interval_minutes=60,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewStudySchedule = new_apps.get_model("schedules", "StudySchedule")
        UserDataset = new_apps.get_model("datasets", "UserDataset")

        tagged_schedule = NewStudySchedule.objects.get(pk=tagged_schedule.pk)
        all_words_schedule = NewStudySchedule.objects.get(pk=all_words_schedule.pk)
        dataset = UserDataset.objects.get(pk=tagged_schedule.dataset_id)

        self.assertEqual(dataset.user_id, user.pk)
        self.assertEqual(dataset.name, f"Расписание #{tagged_schedule.pk}")
        self.assertEqual(list(dataset.tags.values_list("pk", flat=True)), [tag.pk])
        self.assertFalse(dataset.extra_words.exists())
        self.assertIsNone(all_words_schedule.dataset_id)
        self.assertEqual(UserDataset.objects.count(), 1)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        restored_apps = executor.loader.project_state([self.migrate_from]).apps
        RestoredStudySchedule = restored_apps.get_model("schedules", "StudySchedule")
        restored_tagged = RestoredStudySchedule.objects.get(pk=tagged_schedule.pk)
        restored_all_words = RestoredStudySchedule.objects.get(pk=all_words_schedule.pk)

        self.assertEqual(list(restored_tagged.tags.values_list("pk", flat=True)), [tag.pk])
        self.assertFalse(restored_all_words.tags.exists())

        # Reapplying the migration must reconnect the orphan instead of creating
        # a second visible dataset for the same legacy schedule.
        self.assertTrue(UserDataset.objects.filter(pk=dataset.pk).exists())
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        reapplied_apps = executor.loader.project_state([self.migrate_to]).apps
        ReappliedSchedule = reapplied_apps.get_model("schedules", "StudySchedule")
        ReappliedDataset = reapplied_apps.get_model("datasets", "UserDataset")

        self.assertEqual(ReappliedSchedule.objects.get(pk=tagged_schedule.pk).dataset_id, dataset.pk)
        self.assertEqual(ReappliedDataset.objects.filter(user_id=user.pk).count(), 1)

    def test_reverse_preserves_a_dataset_with_user_edits(self):
        User = self.old_apps.get_model("users", "User")
        UserTag = self.old_apps.get_model("tags", "UserTag")
        StudySchedule = self.old_apps.get_model("schedules", "StudySchedule")

        user = User.objects.create(username="migration-edited-user", password="unused")
        tag = UserTag.objects.create(user_id=user.pk, name="Edited")
        schedule = StudySchedule.objects.create(user_id=user.pk, mode="interval", interval_minutes=60)
        schedule.tags.add(tag)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewSchedule = new_apps.get_model("schedules", "StudySchedule")
        UserDataset = new_apps.get_model("datasets", "UserDataset")
        dataset = UserDataset.objects.get(pk=NewSchedule.objects.get(pk=schedule.pk).dataset_id)
        dataset.name = "My edited set"
        dataset.save(update_fields=["name"])
        extra_word = UserWord.objects.create(
            user_id=user.pk,
            word=Word.objects.create(word="migration-extra", part_of_speech=PartOfSpeechChoices.NOUN),
        )
        dataset.extra_words.add(extra_word.pk)

        MigrationExecutor(connection).migrate([self.migrate_from])
        self.assertEqual(UserDataset.objects.get(pk=dataset.pk).name, "My edited set")
        self.assertEqual(
            list(UserDataset.objects.get(pk=dataset.pk).extra_words.values_list("pk", flat=True)), [extra_word.pk]
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        reapplied_apps = executor.loader.project_state([self.migrate_to]).apps
        ReappliedSchedule = reapplied_apps.get_model("schedules", "StudySchedule")
        ReappliedDataset = reapplied_apps.get_model("datasets", "UserDataset")
        self.assertNotEqual(ReappliedSchedule.objects.get(pk=schedule.pk).dataset_id, dataset.pk)
        self.assertEqual(ReappliedDataset.objects.get(pk=dataset.pk).name, "My edited set")
        self.assertEqual(
            list(ReappliedDataset.objects.get(pk=dataset.pk).extra_words.values_list("pk", flat=True)),
            [extra_word.pk],
        )

    def test_reapply_reuses_a_migrated_dataset_with_a_name_suffix(self):
        User = self.old_apps.get_model("users", "User")
        UserTag = self.old_apps.get_model("tags", "UserTag")
        StudySchedule = self.old_apps.get_model("schedules", "StudySchedule")

        user = User.objects.create(username="migration-name-collision", password="unused")
        schedule_tag = UserTag.objects.create(user_id=user.pk, name="Scheduled")
        existing_tag = UserTag.objects.create(user_id=user.pk, name="Other")
        schedule = StudySchedule.objects.create(user_id=user.pk, mode="interval", interval_minutes=60)
        schedule.tags.add(schedule_tag)
        existing = CurrentUserDataset.objects.create(user_id=user.pk, name=f"Расписание #{schedule.pk}")
        existing.tags.add(existing_tag.pk)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewSchedule = new_apps.get_model("schedules", "StudySchedule")
        UserDataset = new_apps.get_model("datasets", "UserDataset")
        first_dataset_id = NewSchedule.objects.get(pk=schedule.pk).dataset_id
        self.assertEqual(UserDataset.objects.get(pk=first_dataset_id).name, f"Расписание #{schedule.pk} (2)")

        MigrationExecutor(connection).migrate([self.migrate_from])
        MigrationExecutor(connection).migrate([self.migrate_to])
        self.assertEqual(NewSchedule.objects.get(pk=schedule.pk).dataset_id, first_dataset_id)
        self.assertEqual(UserDataset.objects.filter(user_id=user.pk).count(), 2)
        self.assertEqual(
            list(UserDataset.objects.get(pk=existing.pk).tags.values_list("pk", flat=True)), [existing_tag.pk]
        )
