from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from tags.models import UserTag
from translations.choices import WordStatusChoices
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word

from datasets.models import UserDataset


class DatasetScheduleFlowsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="flow-user", telegram_id=12345)
        self.bot_auth = {
            "HTTP_X_API_KEY": settings.TG_BOT_AUTH_KEY,
            "HTTP_X_TELEGRAM_ID": str(self.user.telegram_id),
        }

    def create_user_word(self, text: str, *, status: str = WordStatusChoices.LEARNING) -> UserWord:
        word = Word.objects.create(word=text, part_of_speech=PartOfSpeechChoices.NOUN)
        return UserWord.objects.create(user=self.user, word=word, status=status)

    def test_bot_creates_tag_and_extra_word_dataset_then_schedules_it(self):
        verbs = UserTag.objects.create(user=self.user, name="Глаголы")
        nouns = UserTag.objects.create(user=self.user, name="Существительные")
        tagged_words = [self.create_user_word(f"tagged-{index}") for index in range(9)]
        for word in tagged_words[:5]:
            word.tags.add(verbs)
        for word in tagged_words[5:]:
            word.tags.add(nouns)
        extra_word = self.create_user_word("extra")
        self.create_user_word("outside")

        dataset_response = self.client.post(
            "/api/datasets/",
            data={"name": "Немецкий A1", "tags": [verbs.pk, nouns.pk], "extra_words": [extra_word.pk]},
            content_type="application/json",
            **self.bot_auth,
        )
        self.assertEqual(dataset_response.status_code, 201)
        dataset_id = dataset_response.json()["id"]

        schedule_response = self.client.post(
            "/api/schedules/",
            data={
                "dataset_id": dataset_id,
                "is_enabled": True,
                "mode": "interval",
                "items_per_delivery": 10,
                "interval_minutes": 180,
            },
            content_type="application/json",
            **self.bot_auth,
        )
        self.assertEqual(schedule_response.status_code, 201)
        self.assertEqual(schedule_response.json()["dataset_id"], dataset_id)
        self.assertIsNotNone(schedule_response.json()["next_run_at"])
        schedule_id = schedule_response.json()["id"]

        first_run = self.client.post(
            f"/api/schedules/{schedule_id}/runs", data={}, content_type="application/json", **self.bot_auth
        )
        self.assertEqual(first_run.status_code, 201)
        first_ids = {item["user_word"]["id"] for item in first_run.json()["items"]}
        self.assertEqual(first_ids, {word.pk for word in tagged_words} | {extra_word.pk})

        later_word = self.create_user_word("later-tagged")
        later_word.tags.add(verbs)
        second_run = self.client.post(
            f"/api/schedules/{schedule_id}/runs", data={}, content_type="application/json", **self.bot_auth
        )
        self.assertEqual(second_run.status_code, 201)
        second_ids = {item["user_word"]["id"] for item in second_run.json()["items"]}
        self.assertEqual(len(second_ids), 10)
        self.assertIn(later_word.pk, second_ids)

    def test_all_my_words_schedule_needs_no_dataset(self):
        learning_words = [self.create_user_word("eins"), self.create_user_word("zwei")]
        self.create_user_word("paused", status=WordStatusChoices.PAUSED)

        schedule_response = self.client.post(
            "/api/schedules/",
            data={"dataset_id": None, "mode": "interval", "items_per_delivery": 2, "interval_minutes": 180},
            content_type="application/json",
            **self.bot_auth,
        )
        self.assertEqual(schedule_response.status_code, 201)
        self.assertIsNone(schedule_response.json()["dataset_id"])
        self.assertFalse(UserDataset.objects.exists())

        schedule_id = schedule_response.json()["id"]
        run_response = self.client.post(
            f"/api/schedules/{schedule_id}/runs", data={}, content_type="application/json", **self.bot_auth
        )
        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(
            {item["user_word"]["id"] for item in run_response.json()["items"]},
            {word.pk for word in learning_words},
        )
