from datetime import timedelta
from unittest.mock import patch

import jwt
from datasets.models import UserDataset
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone
from translations.choices import WordStatusChoices
from translations.models import BaseTranslation
from translations.schemas import Translation, TranslationResponse
from words.choices import InflectionTypeChoices, PartOfSpeechChoices
from words.models import UserWord, Word, WordInflection

from schedules.models import SiteNotification, StudySchedule
from schedules.services import create_due_schedule_run, create_schedule_run, get_eligible_words


class SiteFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="site-user")
        self.other_user = get_user_model().objects.create_user(username="site-other")
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def add_word(self, text, *, status=WordStatusChoices.LEARNING, user=None):
        word = Word.objects.create(word=text, part_of_speech=PartOfSpeechChoices.VERB)
        return UserWord.objects.create(user=user or self.user, word=word, status=status)

    def add_schedule(self, **overrides):
        values = {
            "user": self.user,
            "mode": StudySchedule.Mode.INTERVAL,
            "interval_minutes": 60,
            "items_per_delivery": 1,
        }
        values.update(overrides)
        return StudySchedule.objects.create(**values)

    def test_inflection_quota_uses_only_words_with_the_requested_form(self):
        first = self.add_word("gehen")
        second = self.add_word("sehen")
        self.add_word("machen")
        WordInflection.objects.create(word=first.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen")
        WordInflection.objects.create(word=second.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gesehen")

        payload = {
            "dataset_id": None,
            "mode": "interval",
            "interval_minutes": 60,
            "exercise_kind": "inflection",
            "inflection_type": "de_partizip_2",
            "items_per_delivery": 3,
        }
        rejected = self.client.post("/api/schedules/", data=payload, content_type="application/json", **self.auth)
        self.assertEqual(rejected.status_code, 422)
        self.assertFalse(StudySchedule.objects.exists())

        payload["items_per_delivery"] = 2
        created = self.client.post("/api/schedules/", data=payload, content_type="application/json", **self.auth)
        self.assertEqual(created.status_code, 201)
        schedule = StudySchedule.objects.get(pk=created.json()["id"])
        self.assertEqual(get_eligible_words(schedule).count(), 2)

        first_run = create_schedule_run(schedule.pk)
        second_run = create_schedule_run(schedule.pk, scheduled_for=timezone.now() + timedelta(minutes=1))
        self.assertEqual(
            set(first_run.items.values_list("user_word_id", flat=True)),
            {first.pk, second.pk},
        )
        self.assertEqual(
            set(second_run.items.values_list("user_word_id", flat=True)),
            {first.pk, second.pk},
        )
        self.assertEqual(SiteNotification.objects.count(), 2)

    def test_changing_exercise_kind_keeps_selection_histories_separate(self):
        first = self.add_word("gehen")
        self.add_word("sehen")
        WordInflection.objects.create(word=first.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen")
        schedule = self.add_schedule(exercise_kind="inflection", inflection_type="de_partizip_2")
        first_run = create_schedule_run(schedule.pk)
        schedule.exercise_kind = "translation"
        schedule.inflection_type = None
        schedule.save(update_fields=["exercise_kind", "inflection_type"])

        original_order_by = QuerySet.order_by

        def order_by_pk_for_random(queryset, *fields):
            return original_order_by(queryset, *("pk",) if fields == ("?",) else fields)

        with patch.object(QuerySet, "order_by", order_by_pk_for_random):
            second_run = create_schedule_run(schedule.pk, scheduled_for=timezone.now() + timedelta(minutes=1))

        self.assertEqual(first_run.exercise_kind, "inflection")
        self.assertEqual(second_run.exercise_kind, "translation")
        self.assertEqual(list(second_run.items.values_list("user_word_id", flat=True)), [first.pk])

    def test_site_notification_can_be_read_without_changing_the_schedule(self):
        self.add_word("gehen")
        due_at = timezone.now() - timedelta(minutes=1)
        schedule = self.add_schedule(is_enabled=True, next_run_at=due_at)
        run = create_due_schedule_run(schedule.pk, now=timezone.now())
        schedule.refresh_from_db()
        next_run_at = schedule.next_run_at

        listed = self.client.get("/api/notifications/", **self.auth)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["run_id"] for item in listed.json()], [run.pk])
        notification_id = listed.json()[0]["id"]
        self.assertIsNone(listed.json()[0]["read_at"])

        read = self.client.post(f"/api/notifications/{notification_id}/read", **self.auth)
        again = self.client.post(f"/api/notifications/{notification_id}/read", **self.auth)
        self.assertEqual(read.status_code, 200)
        self.assertEqual(again.json()["read_at"], read.json()["read_at"])
        self.assertEqual(self.client.get("/api/notifications/", **self.auth).json(), [])
        self.assertEqual(len(self.client.get("/api/notifications/?unread_only=false", **self.auth).json()), 1)
        schedule.refresh_from_db()
        self.assertTrue(schedule.is_enabled)
        self.assertEqual(schedule.next_run_at, next_run_at)

    def test_site_notification_is_private(self):
        self.add_word("gehen", user=self.other_user)
        schedule = StudySchedule.objects.create(user=self.other_user, mode="interval", interval_minutes=60)
        run = create_schedule_run(schedule.pk)
        notification_id = run.site_notification.pk

        self.assertEqual(self.client.get("/api/notifications/", **self.auth).json(), [])
        response = self.client.post(f"/api/notifications/{notification_id}/read", **self.auth)
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(SiteNotification.objects.get(pk=notification_id).read_at)

    def test_card_list_returns_all_dataset_statuses_and_translation_priority(self):
        custom = self.add_word("gehen")
        selected = self.add_word("sehen")
        main = self.add_word("machen", status=WordStatusChoices.PAUSED)
        missing = self.add_word("finden", status=WordStatusChoices.MASTERED)
        self.add_word("outside")
        custom.custom_translation = " мой перевод "
        custom.save(update_fields=["custom_translation"])
        chosen_translation = BaseTranslation.objects.create(
            word=selected.word, target_language="ru", translation="увидеть", is_main=False
        )
        selected.selected_translation = chosen_translation
        selected.save(update_fields=["selected_translation"])
        BaseTranslation.objects.create(word=main.word, target_language="ru", translation="делать", is_main=True)
        dataset = UserDataset.objects.create(user=self.user, name="cards")
        dataset.extra_words.add(custom, selected, main, missing)
        schedule = self.add_schedule(dataset=dataset)

        response = self.client.get(f"/api/schedules/{schedule.pk}/cards", **self.auth)
        self.assertEqual(response.status_code, 200)
        cards = {card["id"]: card for card in response.json()}
        self.assertEqual(set(cards), {custom.pk, selected.pk, main.pk, missing.pk})
        self.assertEqual((cards[custom.pk]["answer"], cards[custom.pk]["answer_source"]), ("мой перевод", "custom"))
        self.assertEqual((cards[selected.pk]["answer"], cards[selected.pk]["answer_source"]), ("увидеть", "selected"))
        self.assertEqual((cards[main.pk]["answer"], cards[main.pk]["answer_source"]), ("делать", "main"))
        self.assertEqual(cards[missing.pk]["status"], WordStatusChoices.MASTERED)
        self.assertIsNone(cards[missing.pk]["answer"])

    def test_inflection_cards_include_missing_forms_for_frontend_filtering(self):
        first = self.add_word("gehen")
        second = self.add_word("sehen", status=WordStatusChoices.PAUSED)
        WordInflection.objects.create(word=first.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen")
        schedule = self.add_schedule(exercise_kind="inflection", inflection_type="de_partizip_2")

        response = self.client.get(f"/api/schedules/{schedule.pk}/cards", **self.auth)
        cards = {card["id"]: card for card in response.json()}
        self.assertEqual(set(cards), {first.pk, second.pk})
        self.assertEqual(cards[first.pk]["answer"], "gegangen")
        self.assertIsNone(cards[second.pk]["answer"])

    def test_update_rejects_inflection_mode_with_too_few_eligible_words(self):
        first = self.add_word("gehen")
        self.add_word("sehen")
        WordInflection.objects.create(word=first.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen")
        schedule = self.add_schedule(is_enabled=True, items_per_delivery=2, next_run_at=timezone.now())

        response = self.client.patch(
            f"/api/schedules/{schedule.pk}",
            data={"exercise_kind": "inflection", "inflection_type": "de_partizip_2"},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        schedule.refresh_from_db()
        self.assertEqual(schedule.exercise_kind, "translation")

    def test_missing_card_translation_is_generated_once_and_saved(self):
        user_word = self.add_word("finden")
        schedule = self.add_schedule()
        ai_result = TranslationResponse(
            word="finden",
            part_of_speech="verb",
            status="success",
            translations=[
                Translation(value="to find", is_main=False),
                Translation(value="to discover", is_main=True),
            ],
        )
        url = f"/api/schedules/{schedule.pk}/cards/{user_word.pk}/resolve-answer"
        with patch("translations.services.get_translation", return_value=ai_result) as generate:
            first = self.client.post(url, **self.auth)
            second = self.client.post(url, **self.auth)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["answer"], "to discover")
        self.assertEqual(first.json()["answer_source"], "main")
        self.assertEqual(second.json()["answer"], "to discover")
        generate.assert_called_once_with(user_word.word, "ru")
        saved = list(BaseTranslation.objects.filter(word=user_word.word).order_by("translation"))
        self.assertEqual(
            [(item.translation, item.is_main) for item in saved], [("to discover", True), ("to find", False)]
        )

    def test_existing_non_main_translation_triggers_generation(self):
        user_word = self.add_word("gehen")
        BaseTranslation.objects.create(word=user_word.word, target_language="ru", translation="to go", is_main=False)
        schedule = self.add_schedule()
        ai_result = TranslationResponse(
            word="gehen",
            part_of_speech="verb",
            status="success",
            translations=[Translation(value="to go", is_main=True)],
        )
        url = f"/api/schedules/{schedule.pk}/cards/{user_word.pk}/resolve-answer"
        with patch("translations.services.get_translation", return_value=ai_result) as generate:
            response = self.client.post(url, **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "to go")
        generate.assert_called_once()
        self.assertEqual(BaseTranslation.objects.filter(word=user_word.word).count(), 1)
        self.assertTrue(BaseTranslation.objects.get(word=user_word.word).is_main)

    def test_untranslatable_card_reports_not_found_without_saving(self):
        user_word = self.add_word("unknown")
        schedule = self.add_schedule()
        ai_result = TranslationResponse(
            word="unknown",
            part_of_speech="verb",
            status="not_found",
            translations=[],
        )
        url = f"/api/schedules/{schedule.pk}/cards/{user_word.pk}/resolve-answer"
        with patch("translations.services.get_translation", return_value=ai_result):
            response = self.client.post(url, **self.auth)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "not_found")
        self.assertFalse(BaseTranslation.objects.filter(word=user_word.word).exists())

    def test_custom_translation_beats_selected_and_main_without_ai(self):
        user_word = self.add_word("gehen")
        user_word.custom_translation = "mine"
        user_word.selected_translation = BaseTranslation.objects.create(
            word=user_word.word, target_language="ru", translation="selected", is_main=False
        )
        user_word.save(update_fields=["custom_translation", "selected_translation"])
        BaseTranslation.objects.create(word=user_word.word, target_language="ru", translation="main", is_main=True)
        schedule = self.add_schedule()
        url = f"/api/schedules/{schedule.pk}/cards/{user_word.pk}/resolve-answer"

        with patch("translations.services.get_translation") as generate:
            response = self.client.post(url, **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "mine")
        self.assertEqual(response.json()["answer_source"], "custom")
        generate.assert_not_called()

    def test_card_answer_cannot_be_resolved_outside_schedule_dataset(self):
        inside = self.add_word("gehen")
        outside = self.add_word("sehen")
        dataset = UserDataset.objects.create(user=self.user, name="only one")
        dataset.extra_words.add(inside)
        schedule = self.add_schedule(dataset=dataset)
        url = f"/api/schedules/{schedule.pk}/cards/{outside.pk}/resolve-answer"

        with patch("translations.services.get_translation") as generate:
            response = self.client.post(url, **self.auth)

        self.assertEqual(response.status_code, 404)
        generate.assert_not_called()
