from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from tags.models import UserTag
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word

from schedules.models import FixedScheduleTime, ScheduleRun, ScheduleRunItem, StudySchedule


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

    def test_schedule_cannot_send_the_same_word_twice_on_one_local_date(self):
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

        with self.assertRaises(IntegrityError), transaction.atomic():
            ScheduleRunItem.objects.create(
                run=second_run,
                schedule=schedule,
                user_word=self.user_word,
                position=1,
                local_date=scheduled_for.date(),
            )
