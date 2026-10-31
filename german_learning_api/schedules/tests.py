from datetime import time, timedelta

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from tags.models import UserTag
from translations.choices import WordStatusChoices
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word

from schedules.models import FixedScheduleTime, ScheduleRun, ScheduleRunItem, StudySchedule
from schedules.services import InsufficientLearningWordsError, create_schedule_run


class StudyScheduleModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="schedule-user", password="password")
        self.tag = UserTag.objects.create(user=self.user, name="schedule-tag")
        self.word = Word.objects.create(word="Haus", part_of_speech=PartOfSpeechChoices.NOUN)
        self.user_word = UserWord.objects.create(user=self.user, word=self.word)

    def create_schedule(self, **overrides):
        values = {
            "user": self.user,
            "mode": StudySchedule.Mode.INTERVAL,
            "interval_minutes": 60,
        }
        values.update(overrides)
        schedule = StudySchedule.objects.create(**values)
        schedule.tags.add(self.tag)
        return schedule

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
            delivery_format=StudySchedule.DeliveryFormat.WORDS,
        )
        second_run = ScheduleRun.objects.create(
            schedule=schedule,
            scheduled_for=scheduled_for + timedelta(hours=1),
            delivery_format=StudySchedule.DeliveryFormat.WORDS,
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
        tags: tuple[UserTag, ...] = (),
    ) -> StudySchedule:
        schedule = StudySchedule.objects.create(
            user=self.user,
            mode=StudySchedule.Mode.INTERVAL,
            interval_minutes=60,
            items_per_delivery=items_per_delivery,
        )
        schedule.tags.add(*tags)
        return schedule

    def get_item_ids(self, run: ScheduleRun) -> set[int]:
        return set(run.items.values_list("user_word_id", flat=True))

    def test_empty_tag_selection_uses_all_learning_words(self):
        first_word = self.create_user_word("eins")
        second_word = self.create_user_word("zwei")
        self.create_user_word("drei", status=WordStatusChoices.PAUSED)
        self.create_user_word("vier", status=WordStatusChoices.MASTERED)
        schedule = self.create_schedule(items_per_delivery=2)

        run = create_schedule_run(schedule.pk)

        self.assertEqual(self.get_item_ids(run), {first_word.pk, second_word.pk})

    def test_selected_tags_limit_the_word_pool(self):
        first_selected_word = self.create_user_word("eins", tags=(self.selected_tag,))
        second_selected_word = self.create_user_word("zwei", tags=(self.selected_tag,))
        self.create_user_word("drei", tags=(self.other_tag,))
        self.create_user_word("vier")
        schedule = self.create_schedule(items_per_delivery=2, tags=(self.selected_tag,))

        run = create_schedule_run(schedule.pk)

        self.assertEqual(self.get_item_ids(run), {first_selected_word.pk, second_selected_word.pk})

    def test_insufficient_learning_words_does_not_create_a_run(self):
        self.create_user_word("eins")
        schedule = self.create_schedule(items_per_delivery=2)

        with self.assertRaises(InsufficientLearningWordsError) as context:
            create_schedule_run(schedule.pk)

        self.assertEqual(context.exception.available_count, 1)
        self.assertEqual(context.exception.required_count, 2)
        self.assertFalse(ScheduleRun.objects.filter(schedule=schedule).exists())

    def test_next_run_prioritizes_remaining_new_words_before_repeats(self):
        words = [self.create_user_word(f"word-{index}") for index in range(6)]
        schedule = self.create_schedule(items_per_delivery=5)
        scheduled_for = timezone.now()

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
        scheduled_for = timezone.now()

        first_run = create_schedule_run(schedule.pk, scheduled_for=scheduled_for)
        second_run = create_schedule_run(
            schedule.pk,
            scheduled_for=scheduled_for + timedelta(minutes=1),
        )

        self.assertEqual(self.get_item_ids(first_run), self.get_item_ids(second_run))


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
        self.assertEqual(body["status"], ScheduleRun.Status.PENDING)
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
