from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch

import jwt
from datasets.models import UserDataset
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone
from tags.models import UserTag
from translations.choices import WordStatusChoices
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word

from schedules.errors import InsufficientLearningWordsError
from schedules.models import FixedScheduleTime, ScheduleRun, ScheduleRunItem, StudySchedule
from schedules.services import (
    calculate_next_run_at,
    create_due_schedule_run,
    create_schedule_run,
    get_eligible_words,
    validate_schedule_pool,
)
from schedules.tasks import dispatch_due_schedules, process_due_schedule


class StudyScheduleModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="schedule-user", password="password")
        self.word = Word.objects.create(word="Haus", part_of_speech=PartOfSpeechChoices.NOUN)
        self.user_word = UserWord.objects.create(user=self.user, word=self.word)

    def create_schedule(self, **overrides):
        values = {
            "user": self.user,
            "mode": StudySchedule.Mode.INTERVAL,
            "interval_minutes": 60,
        }
        values.update(overrides)
        return StudySchedule.objects.create(**values)

    def test_interval_requires_a_positive_interval(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudySchedule.objects.create(
                user=self.user,
                mode=StudySchedule.Mode.INTERVAL,
                interval_minutes=None,
            )

    def test_fixed_times_mode_rejects_an_interval(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudySchedule.objects.create(
                user=self.user,
                mode=StudySchedule.Mode.FIXED_TIMES,
                interval_minutes=60,
            )

    def test_fixed_time_is_limited_to_five_slots(self):
        schedule = self.create_schedule(
            mode=StudySchedule.Mode.FIXED_TIMES,
            interval_minutes=None,
        )

        FixedScheduleTime.objects.create(schedule=schedule, slot=5, local_time=time(10, 0))

        with self.assertRaises(IntegrityError), transaction.atomic():
            FixedScheduleTime.objects.create(schedule=schedule, slot=6, local_time=time(11, 0))

    def test_schedule_can_repeat_a_word_on_one_local_date(self):
        schedule = self.create_schedule()
        scheduled_for = timezone.now()
        first_run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=scheduled_for,
        )
        second_run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=scheduled_for + timedelta(hours=1),
        )
        ScheduleRunItem.objects.create(
            run=first_run,
            schedule=schedule,
            user_word=self.user_word,
            position=1,
            local_date=scheduled_for.date(),
        )

        ScheduleRunItem.objects.create(
            run=second_run,
            schedule=schedule,
            user_word=self.user_word,
            position=1,
            local_date=scheduled_for.date(),
        )

        self.assertEqual(ScheduleRunItem.objects.filter(schedule=schedule).count(), 2)

    def test_deleting_user_cascades_its_dataset_and_schedule(self):
        dataset = UserDataset.objects.create(user=self.user, name="owned")
        schedule = self.create_schedule(dataset=dataset)
        user_id = self.user.pk
        dataset_id = dataset.pk
        schedule_id = schedule.pk

        self.user.delete()

        self.assertFalse(get_user_model().objects.filter(pk=user_id).exists())
        self.assertFalse(UserDataset.objects.filter(pk=dataset_id).exists())
        self.assertFalse(StudySchedule.objects.filter(pk=schedule_id).exists())


class ScheduleRunSelectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="selection-user", password="password")
        self.selected_tag = UserTag.objects.create(user=self.user, name="selected")
        self.other_tag = UserTag.objects.create(user=self.user, name="other")

    def create_user_word(
        self,
        name: str,
        *,
        status: WordStatusChoices = WordStatusChoices.LEARNING,
        tags: tuple[UserTag, ...] = (),
    ) -> UserWord:
        word = Word.objects.create(word=name, part_of_speech=PartOfSpeechChoices.NOUN)
        user_word = UserWord.objects.create(user=self.user, word=word, status=status)
        user_word.tags.add(*tags)
        return user_word

    def create_schedule(
        self,
        *,
        items_per_delivery: int,
        dataset: UserDataset | None = None,
    ) -> StudySchedule:
        return StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
            items_per_delivery=items_per_delivery,
            dataset=dataset,
        )

    def create_dataset(
        self,
        *,
        tags: tuple[UserTag, ...] = (),
        extra_words: tuple[UserWord, ...] = (),
    ) -> UserDataset:
        dataset = UserDataset.objects.create(user=self.user, name=f"dataset-{UserDataset.objects.count() + 1}")
        dataset.tags.add(*tags)
        dataset.extra_words.add(*extra_words)
        return dataset

    def get_item_ids(self, run: ScheduleRun) -> set[int]:
        return set(run.items.values_list("user_word_id", flat=True))

    def test_null_dataset_uses_all_learning_words(self):
        first_word = self.create_user_word("eins")
        second_word = self.create_user_word("zwei")
        self.create_user_word("drei", status=WordStatusChoices.PAUSED)
        self.create_user_word("vier", status=WordStatusChoices.MASTERED)
        schedule = self.create_schedule(items_per_delivery=2)

        run = create_schedule_run(schedule.pk)

        self.assertEqual(self.get_item_ids(run), {first_word.pk, second_word.pk})

    def test_dataset_tags_limit_the_word_pool(self):
        first_selected_word = self.create_user_word("eins", tags=(self.selected_tag,))
        second_selected_word = self.create_user_word("zwei", tags=(self.selected_tag,))
        self.create_user_word("drei", tags=(self.other_tag,))
        self.create_user_word("vier")
        dataset = self.create_dataset(tags=(self.selected_tag,))
        schedule = self.create_schedule(items_per_delivery=2, dataset=dataset)

        run = create_schedule_run(schedule.pk)

        self.assertEqual(self.get_item_ids(run), {first_selected_word.pk, second_selected_word.pk})

    def test_dataset_combines_tag_words_and_extra_words_without_duplicates(self):
        tagged_word = self.create_user_word("eins", tags=(self.selected_tag,))
        overlap_word = self.create_user_word("zwei", tags=(self.selected_tag,))
        extra_word = self.create_user_word("drei")
        self.create_user_word("vier", tags=(self.other_tag,))
        paused_word = self.create_user_word("fuenf", status=WordStatusChoices.PAUSED)
        dataset = self.create_dataset(
            tags=(self.selected_tag,),
            extra_words=(overlap_word, extra_word, paused_word),
        )
        schedule = self.create_schedule(items_per_delivery=3, dataset=dataset)

        run = create_schedule_run(schedule.pk)

        self.assertEqual(self.get_item_ids(run), {tagged_word.pk, overlap_word.pk, extra_word.pk})
        self.assertEqual(run.items.count(), 3)

    def test_random_selection_deduplicates_a_word_with_multiple_dataset_tags(self):
        overlapping_word = self.create_user_word("eins", tags=(self.selected_tag, self.other_tag))
        second_word = self.create_user_word("zwei", tags=(self.selected_tag,))
        dataset = self.create_dataset(tags=(self.selected_tag, self.other_tag))
        schedule = self.create_schedule(items_per_delivery=2, dataset=dataset)

        random_order_ids = list(get_eligible_words(schedule).order_by("?").values_list("pk", flat=True))
        run = create_schedule_run(schedule.pk)

        self.assertCountEqual(random_order_ids, [overlapping_word.pk, second_word.pk])
        self.assertEqual(self.get_item_ids(run), {overlapping_word.pk, second_word.pk})

    def test_new_words_added_to_a_dataset_tag_join_the_next_run(self):
        self.create_user_word("eins", tags=(self.selected_tag,))
        dataset = self.create_dataset(tags=(self.selected_tag,))
        schedule = self.create_schedule(items_per_delivery=1, dataset=dataset)
        scheduled_for = timezone.now()

        create_schedule_run(schedule.pk, scheduled_for=scheduled_for)
        added_word = self.create_user_word("zwei", tags=(self.selected_tag,))
        second_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for + timedelta(minutes=1))

        self.assertEqual(self.get_item_ids(second_run), {added_word.pk})

    def test_switching_a_schedule_dataset_changes_the_next_run_pool(self):
        first_word = self.create_user_word("eins")
        second_word = self.create_user_word("zwei")
        first_dataset = self.create_dataset(extra_words=(first_word,))
        second_dataset = self.create_dataset(extra_words=(second_word,))
        schedule = self.create_schedule(items_per_delivery=1, dataset=first_dataset)
        scheduled_for = timezone.now()

        first_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for)
        schedule.dataset = second_dataset
        schedule.save(update_fields=["dataset"])
        second_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for + timedelta(minutes=1))

        self.assertEqual(self.get_item_ids(first_run), {first_word.pk})
        self.assertEqual(self.get_item_ids(second_run), {second_word.pk})

    def test_two_schedules_see_new_extra_and_tag_words_in_a_shared_dataset(self):
        initial_word = self.create_user_word("eins", tags=(self.selected_tag,))
        dataset = self.create_dataset(tags=(self.selected_tag,))
        schedules = [self.create_schedule(items_per_delivery=1, dataset=dataset) for _ in range(2)]
        scheduled_for = timezone.now()

        first_runs = [create_schedule_run(schedule.pk, scheduled_for=scheduled_for) for schedule in schedules]
        self.assertTrue(all(self.get_item_ids(run) == {initial_word.pk} for run in first_runs))

        extra_word = self.create_user_word("zwei")
        dataset.extra_words.add(extra_word)
        second_runs = [
            create_schedule_run(schedule.pk, scheduled_for=scheduled_for + timedelta(minutes=1))
            for schedule in schedules
        ]
        self.assertTrue(all(self.get_item_ids(run) == {extra_word.pk} for run in second_runs))

        tagged_word = self.create_user_word("drei", tags=(self.selected_tag,))
        third_runs = [
            create_schedule_run(schedule.pk, scheduled_for=scheduled_for + timedelta(minutes=2))
            for schedule in schedules
        ]
        self.assertTrue(all(self.get_item_ids(run) == {tagged_word.pk} for run in third_runs))

    def test_insufficient_learning_words_does_not_create_a_run(self):
        self.create_user_word("eins")
        schedule = self.create_schedule(items_per_delivery=2)

        with self.assertRaises(InsufficientLearningWordsError):
            create_schedule_run(schedule.pk)

        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

    def test_next_run_prioritizes_remaining_new_words_before_repeats(self):
        words = [self.create_user_word(f"word-{index}") for index in range(6)]
        schedule = self.create_schedule(items_per_delivery=5)
        scheduled_for = datetime(2026, 1, 1, 12, tzinfo=UTC)

        first_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for)
        second_run = create_schedule_run(
            schedule.pk,
            scheduled_for=scheduled_for + timedelta(minutes=1),
        )

        all_word_ids = {word.pk for word in words}
        first_run_ids = self.get_item_ids(first_run)
        second_run_ids = self.get_item_ids(second_run)
        remaining_new_ids = all_word_ids - first_run_ids

        self.assertEqual(len(first_run_ids), 5)
        self.assertEqual(len(second_run_ids), 5)
        self.assertEqual(second_run_ids - first_run_ids, remaining_new_ids)
        self.assertEqual(len(second_run_ids & first_run_ids), 4)

    def test_words_can_repeat_in_a_later_run_on_the_same_local_date(self):
        [self.create_user_word(f"word-{index}") for index in range(5)]
        schedule = self.create_schedule(items_per_delivery=5)
        scheduled_for = datetime(2026, 1, 1, 12, tzinfo=UTC)

        first_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for)
        second_run = create_schedule_run(
            schedule.pk,
            scheduled_for=scheduled_for + timedelta(minutes=1),
        )

        self.assertEqual(self.get_item_ids(first_run), self.get_item_ids(second_run))

    def test_word_shown_yesterday_precedes_a_repeat_from_today(self):
        today_word = self.create_user_word("today")
        yesterday_word = self.create_user_word("yesterday")
        dataset = self.create_dataset(extra_words=(today_word, yesterday_word))
        schedule = self.create_schedule(items_per_delivery=1, dataset=dataset)
        schedule.timezone = "Europe/Moscow"
        schedule.save(update_fields=["timezone"])

        yesterday_run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=datetime(2026, 1, 2, 18, 30, tzinfo=UTC),
        )
        ScheduleRunItem.objects.create(
            run=yesterday_run,
            schedule=schedule,
            user_word=yesterday_word,
            position=1,
            local_date=date(2026, 1, 2),
        )
        today_run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=datetime(2026, 1, 2, 21, 30, tzinfo=UTC),
        )
        ScheduleRunItem.objects.create(
            run=today_run,
            schedule=schedule,
            user_word=today_word,
            position=1,
            local_date=date(2026, 1, 3),
        )

        original_order_by = QuerySet.order_by

        def use_pk_order_for_random(queryset, *fields):
            return original_order_by(queryset, *("pk",) if fields == ("?",) else fields)

        with patch.object(QuerySet, "order_by", use_pk_order_for_random):
            run = create_schedule_run(schedule.pk, scheduled_for=datetime(2026, 1, 2, 22, 30, tzinfo=UTC))

        self.assertEqual(list(run.items.values_list("user_word_id", flat=True)), [yesterday_word.pk])
        self.assertEqual(list(run.items.values_list("local_date", flat=True)), [date(2026, 1, 3)])


class ScheduleRunApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="api-user", password="password")

    def create_schedule(self, *, items_per_delivery: int) -> StudySchedule:
        return StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
            items_per_delivery=items_per_delivery,
        )

    def create_learning_word(self, name: str) -> UserWord:
        word = Word.objects.create(word=name, part_of_speech=PartOfSpeechChoices.NOUN)
        return UserWord.objects.create(user=self.user, word=word)

    def get_authorization_header(self) -> str:
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        return f"Bearer {token}"

    def test_endpoint_creates_a_pending_run_with_selected_words(self):
        schedule = self.create_schedule(items_per_delivery=2)
        self.create_learning_word("eins")
        self.create_learning_word("zwei")

        response = self.client.post(
            f"/api/schedules/{schedule.pk}/runs",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["exercise_kind"], StudySchedule.ExerciseKind.TRANSLATION)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual([item["position"] for item in body["items"]], [1, 2])
        self.assertEqual(ScheduleRun.objects.filter(schedule=schedule).count(), 1)

    def test_endpoint_rejects_a_pool_smaller_than_the_delivery_size(self):
        schedule = self.create_schedule(items_per_delivery=2)
        self.create_learning_word("eins")

        response = self.client.post(
            f"/api/schedules/{schedule.pk}/runs",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "insufficient_learning_words")
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())


class NextRunCalculationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="next-run-user", password="password")

    def create_interval_schedule(self, interval_minutes: int) -> StudySchedule:
        return StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=interval_minutes,
        )

    def create_fixed_schedule(self, *fixed_times: time) -> StudySchedule:
        schedule = StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.FIXED_TIMES,
            interval_minutes=None,
            timezone="Europe/Moscow",
        )
        for slot, local_time in enumerate(fixed_times, start=1):
            FixedScheduleTime.objects.create(
                schedule=schedule,
                slot=slot,
                local_time=local_time,
            )
        return schedule

    def test_interval_next_run_is_relative_to_the_reference_time(self):
        schedule = self.create_interval_schedule(interval_minutes=60)
        reference_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        self.assertEqual(
            calculate_next_run_at(schedule, reference_at=reference_at),
            datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
        )

    def test_fixed_time_next_run_uses_the_schedule_timezone(self):
        schedule = self.create_fixed_schedule(time(10, 0), time(15, 0))
        reference_at = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)

        self.assertEqual(
            calculate_next_run_at(schedule, reference_at=reference_at),
            datetime(2026, 1, 1, 7, 0, tzinfo=UTC),
        )

    def test_fixed_time_next_run_moves_to_the_next_local_day_when_needed(self):
        schedule = self.create_fixed_schedule(time(10, 0), time(15, 0))
        reference_at = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)

        self.assertEqual(
            calculate_next_run_at(schedule, reference_at=reference_at),
            datetime(2026, 1, 2, 7, 0, tzinfo=UTC),
        )


class StudyScheduleApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="schedule-api-user", password="password")

    def get_authorization_header(self) -> str:
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        return f"Bearer {token}"

    def create_learning_word(self, name: str) -> UserWord:
        word = Word.objects.create(word=name, part_of_speech=PartOfSpeechChoices.NOUN)
        return UserWord.objects.create(user=self.user, word=word)

    def create_interval_schedule(self, *, items_per_delivery: int = 2) -> StudySchedule:
        return StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
            items_per_delivery=items_per_delivery,
        )

    def post_schedule(self, payload: dict):
        return self.client.post(
            "/api/schedules/",
            data={"dataset_id": None, **payload},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

    def patch_schedule(self, schedule: StudySchedule, payload: dict):
        return self.client.patch(
            f"/api/schedules/{schedule.pk}",
            data=payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

    def test_create_enabled_interval_schedule_validates_the_pool_and_sets_next_run(self):
        self.create_learning_word("eins")
        self.create_learning_word("zwei")

        response = self.post_schedule(
            {
                "is_enabled": True,
                "mode": "interval",
                "items_per_delivery": 2,
                "timezone": "UTC",
                "interval_minutes": 60,
            }
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["is_enabled"])
        self.assertIsNotNone(body["next_run_at"])
        self.assertIsNone(body["dataset_id"])
        self.assertTrue(StudySchedule.objects.get(pk=body["id"]).is_enabled)

    def test_create_schedule_requires_an_explicit_dataset_choice(self):
        response = self.client.post(
            "/api/schedules/",
            data={"mode": "interval", "interval_minutes": 60},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(StudySchedule.objects.exists())

    def test_create_schedule_rejects_another_users_dataset(self):
        other_user = get_user_model().objects.create_user(username="foreign-dataset-user", password="password")
        dataset = UserDataset.objects.create(user=other_user, name="foreign")
        self.create_learning_word("eins")

        response = self.post_schedule({"interval_minutes": 60, "dataset_id": dataset.pk})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_dataset_id")
        self.assertFalse(StudySchedule.objects.exists())

    def test_update_switches_between_a_dataset_and_all_words(self):
        selected_word = self.create_learning_word("eins")
        self.create_learning_word("zwei")
        dataset = UserDataset.objects.create(user=self.user, name="selected")
        dataset.extra_words.add(selected_word)
        schedule = self.create_interval_schedule(items_per_delivery=1)

        selected_response = self.patch_schedule(schedule, {"dataset_id": dataset.pk})
        unchanged_response = self.patch_schedule(schedule, {"items_per_delivery": 1})
        all_words_response = self.patch_schedule(schedule, {"dataset_id": None})

        self.assertEqual(selected_response.status_code, 200)
        self.assertEqual(selected_response.json()["dataset_id"], dataset.pk)
        self.assertEqual(unchanged_response.status_code, 200)
        self.assertEqual(unchanged_response.json()["dataset_id"], dataset.pk)
        self.assertEqual(all_words_response.status_code, 200)
        self.assertIsNone(all_words_response.json()["dataset_id"])
        schedule.refresh_from_db()
        self.assertIsNone(schedule.dataset_id)

    def test_update_rejects_another_users_dataset_without_changing_the_schedule(self):
        self.create_learning_word("eins")
        schedule = self.create_interval_schedule(items_per_delivery=1)
        other_user = get_user_model().objects.create_user(username="foreign-patch-user", password="password")
        dataset = UserDataset.objects.create(user=other_user, name="foreign")

        response = self.patch_schedule(schedule, {"dataset_id": dataset.pk})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_dataset_id")
        schedule.refresh_from_db()
        self.assertIsNone(schedule.dataset_id)

    def test_bot_can_list_the_users_schedules(self):
        self.user.telegram_id = 123456789
        self.user.save(update_fields=["telegram_id"])
        schedule = self.create_interval_schedule(items_per_delivery=1)

        response = self.client.get(
            "/api/schedules/",
            HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY,
            HTTP_X_TELEGRAM_ID=str(self.user.telegram_id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [schedule.pk])

    def test_create_schedule_rejects_an_insufficient_pool(self):
        self.create_learning_word("eins")

        response = self.post_schedule(
            {
                "is_enabled": True,
                "mode": "interval",
                "items_per_delivery": 2,
                "interval_minutes": 60,
            }
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "insufficient_learning_words")
        self.assertFalse(StudySchedule.objects.exists())

    def test_create_schedule_reports_the_specific_configuration_error(self):
        self.create_learning_word("eins")

        response = self.post_schedule({"mode": "interval", "items_per_delivery": 1})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "interval_minutes_required")

    def test_create_fixed_schedule_sorts_times_and_assigns_slots(self):
        self.create_learning_word("eins")
        self.create_learning_word("zwei")

        response = self.post_schedule(
            {
                "is_enabled": True,
                "mode": "fixed_times",
                "items_per_delivery": 2,
                "timezone": "Europe/Moscow",
                "fixed_times": ["15:00:00", "10:00:00"],
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["fixed_times"],
            [
                {"slot": 1, "local_time": "10:00:00"},
                {"slot": 2, "local_time": "15:00:00"},
            ],
        )

    def test_update_rejects_a_configuration_that_outgrows_the_pool(self):
        self.create_learning_word("eins")
        self.create_learning_word("zwei")
        schedule = self.create_interval_schedule(items_per_delivery=2)
        schedule.is_enabled = True
        schedule.next_run_at = timezone.now() + timedelta(hours=1)
        schedule.save(update_fields=["is_enabled", "next_run_at"])

        response = self.client.patch(
            f"/api/schedules/{schedule.pk}",
            data={"items_per_delivery": 3},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 422)
        schedule.refresh_from_db()
        self.assertEqual(schedule.items_per_delivery, 2)

    def test_disabled_schedule_still_requires_enough_words_on_creation(self):
        dataset = UserDataset.objects.create(user=self.user, name="draft")

        rejected = self.post_schedule(
            {
                "dataset_id": dataset.pk,
                "is_enabled": False,
                "items_per_delivery": 2,
                "interval_minutes": 60,
            }
        )

        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["detail"], "insufficient_learning_words")
        self.assertFalse(StudySchedule.objects.exists())

        dataset.extra_words.add(self.create_learning_word("eins"), self.create_learning_word("zwei"))
        created = self.post_schedule(
            {
                "dataset_id": dataset.pk,
                "is_enabled": False,
                "items_per_delivery": 2,
                "interval_minutes": 60,
            }
        )
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.json()["next_run_at"])
        schedule = StudySchedule.objects.get(pk=created.json()["id"])
        enabled = self.patch_schedule(schedule, {"is_enabled": True})

        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.json()["is_enabled"])
        self.assertIsNotNone(enabled.json()["next_run_at"])

    def test_shrunken_dataset_can_be_disabled_and_edited_before_reenabling(self):
        word = self.create_learning_word("eins")
        dataset = UserDataset.objects.create(user=self.user, name="changing")
        dataset.extra_words.add(word)
        schedule = self.create_interval_schedule(items_per_delivery=1)
        schedule.dataset = dataset
        schedule.is_enabled = True
        schedule.next_run_at = timezone.now() + timedelta(hours=1)
        schedule.save(update_fields=["dataset", "is_enabled", "next_run_at"])
        dataset.extra_words.remove(word)

        disabled = self.patch_schedule(schedule, {"is_enabled": False})
        edited = self.patch_schedule(schedule, {"items_per_delivery": 2})
        rejected = self.patch_schedule(schedule, {"is_enabled": True})

        self.assertEqual(disabled.status_code, 200)
        self.assertIsNone(disabled.json()["next_run_at"])
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["items_per_delivery"], 2)
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(rejected.json()["detail"], "insufficient_learning_words")
        schedule.refresh_from_db()
        self.assertFalse(schedule.is_enabled)
        self.assertEqual(schedule.items_per_delivery, 2)
        self.assertIsNone(schedule.next_run_at)

    def test_update_enables_a_schedule_and_calculates_the_next_run(self):
        self.create_learning_word("eins")
        self.create_learning_word("zwei")
        schedule = self.create_interval_schedule()

        response = self.client.patch(
            f"/api/schedules/{schedule.pk}",
            data={"is_enabled": True},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_enabled"])
        self.assertIsNotNone(response.json()["next_run_at"])

    def test_update_switches_an_interval_schedule_to_fixed_times(self):
        self.create_learning_word("eins")
        self.create_learning_word("zwei")
        schedule = self.create_interval_schedule()

        response = self.client.patch(
            f"/api/schedules/{schedule.pk}",
            data={
                "is_enabled": True,
                "mode": "fixed_times",
                "timezone": "Europe/Moscow",
                "fixed_times": ["15:00:00", "10:00:00"],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], StudySchedule.Mode.FIXED_TIMES)
        self.assertIsNone(body["interval_minutes"])
        self.assertEqual(
            body["fixed_times"],
            [
                {"slot": 1, "local_time": "10:00:00"},
                {"slot": 2, "local_time": "15:00:00"},
            ],
        )
        self.assertIsNotNone(body["next_run_at"])

    def test_list_and_delete_only_affect_the_current_users_schedules(self):
        own_schedule = self.create_interval_schedule()
        other_user = get_user_model().objects.create_user(username="other-schedule-user", password="password")
        other_schedule = StudySchedule.objects.create(
            user=other_user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
        )

        list_response = self.client.get(
            "/api/schedules/",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )
        delete_response = self.client.delete(
            f"/api/schedules/{own_schedule.pk}",
            HTTP_AUTHORIZATION=self.get_authorization_header(),
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()], [own_schedule.pk])
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(StudySchedule.objects.filter(pk=own_schedule.pk).exists())
        self.assertTrue(StudySchedule.objects.filter(pk=other_schedule.pk).exists())


class CeleryScheduleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="celery-schedule-user", password="password")
        word = Word.objects.create(word="Haus", part_of_speech=PartOfSpeechChoices.NOUN)
        UserWord.objects.create(user=self.user, word=word)

    def create_schedule(self, *, due_at: datetime, is_enabled: bool = True) -> StudySchedule:
        return StudySchedule.objects.create(
            user=self.user,
            is_enabled=is_enabled,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
            items_per_delivery=1,
            next_run_at=due_at,
        )

    def test_dispatcher_enqueues_only_enabled_due_schedules(self):
        now = timezone.now()
        due = self.create_schedule(due_at=now - timedelta(minutes=1))
        self.create_schedule(due_at=now + timedelta(hours=1))
        self.create_schedule(due_at=now - timedelta(minutes=1), is_enabled=False)

        with patch("schedules.tasks.process_due_schedule.delay") as enqueue:
            dispatch_due_schedules.run()

        enqueue.assert_called_once_with(due.pk)

    def test_due_run_is_saved_once_and_advances_from_the_original_slot(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at)

        run = create_due_schedule_run(schedule.pk, now=due_at + timedelta(minutes=5))
        duplicate = create_due_schedule_run(schedule.pk, now=due_at + timedelta(minutes=5))

        schedule.refresh_from_db()
        self.assertIsNone(duplicate)
        self.assertEqual(run.scheduled_for, due_at)
        self.assertEqual(run.items.count(), 1)
        self.assertEqual(schedule.next_run_at, due_at + timedelta(hours=1))
        self.assertEqual(ScheduleRun.objects.filter(schedule=schedule).count(), 1)

    def test_late_worker_skips_missed_intervals(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at)

        create_due_schedule_run(schedule.pk, now=due_at + timedelta(hours=2, minutes=30))

        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_at, due_at + timedelta(hours=3))
        self.assertEqual(ScheduleRun.objects.filter(schedule=schedule).count(), 1)

    def test_fixed_times_advance_in_the_schedule_timezone(self):
        schedule = StudySchedule.objects.create(
            user=self.user,
            is_enabled=True,
            mode=StudySchedule.Mode.FIXED_TIMES,
            timezone="Europe/Moscow",
            interval_minutes=None,
            next_run_at=datetime(2026, 1, 1, 7, tzinfo=UTC),
        )
        FixedScheduleTime.objects.create(schedule=schedule, slot=1, local_time=time(10))
        FixedScheduleTime.objects.create(schedule=schedule, slot=2, local_time=time(15))

        run = create_due_schedule_run(schedule.pk, now=datetime(2026, 1, 1, 7, 1, tzinfo=UTC))

        schedule.refresh_from_db()
        self.assertEqual(run.scheduled_for, datetime(2026, 1, 1, 7, tzinfo=UTC))
        self.assertEqual(schedule.next_run_at, datetime(2026, 1, 1, 12, tzinfo=UTC))

    def test_disabled_schedule_does_not_create_a_run(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at, is_enabled=False)

        self.assertIsNone(create_due_schedule_run(schedule.pk, now=due_at))
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

    def test_insufficient_pool_skips_the_due_slot_and_uses_the_next_one(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at)
        schedule.items_per_delivery = 2
        schedule.save(update_fields=["items_per_delivery"])

        skipped_run = create_due_schedule_run(schedule.pk, now=due_at)

        schedule.refresh_from_db()
        self.assertIsNone(skipped_run)
        self.assertEqual(schedule.next_run_at, due_at + timedelta(hours=1))
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

        second_word = Word.objects.create(word="Baum", part_of_speech=PartOfSpeechChoices.NOUN)
        UserWord.objects.create(user=self.user, word=second_word)
        next_run = create_due_schedule_run(schedule.pk, now=due_at + timedelta(hours=1))

        self.assertIsNotNone(next_run)
        self.assertEqual(next_run.scheduled_for, due_at + timedelta(hours=1))
        self.assertEqual(next_run.items.count(), 2)

    def test_dataset_shrinkage_skips_a_due_slot_until_words_are_added(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at)
        user_word = UserWord.objects.get(user=self.user)
        dataset = UserDataset.objects.create(user=self.user, name="changing")
        dataset.extra_words.add(user_word)
        schedule.dataset = dataset
        schedule.save(update_fields=["dataset"])
        dataset.extra_words.remove(user_word)

        self.assertIsNone(create_due_schedule_run(schedule.pk, now=due_at))
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_at, due_at + timedelta(hours=1))
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

        dataset.extra_words.add(user_word)
        next_run = create_due_schedule_run(schedule.pk, now=due_at + timedelta(hours=1))

        self.assertIsNotNone(next_run)
        self.assertEqual(list(next_run.items.values_list("user_word_id", flat=True)), [user_word.pk])

    def test_pool_shrinkage_during_selection_skips_the_due_slot(self):
        due_at = datetime(2026, 1, 1, 12, tzinfo=UTC)
        schedule = self.create_schedule(due_at=due_at)
        user_word = UserWord.objects.get(user=self.user)
        dataset = UserDataset.objects.create(user=self.user, name="concurrent change")
        dataset.extra_words.add(user_word)
        schedule.dataset = dataset
        schedule.save(update_fields=["dataset"])

        def shrink_after_count(locked_schedule):
            available_count = validate_schedule_pool(locked_schedule)
            dataset.extra_words.remove(user_word)
            return available_count

        with patch("schedules.services.validate_schedule_pool", side_effect=shrink_after_count):
            run = create_due_schedule_run(schedule.pk, now=due_at)

        schedule.refresh_from_db()
        self.assertIsNone(run)
        self.assertEqual(schedule.next_run_at, due_at + timedelta(hours=1))
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

    def test_task_uses_the_service_for_due_schedules(self):
        due_at = timezone.now() - timedelta(minutes=1)
        schedule = self.create_schedule(due_at=due_at)

        process_due_schedule.run(schedule.pk)

        self.assertEqual(ScheduleRun.objects.get(schedule=schedule).scheduled_for, due_at)
