import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from words.choices import InflectionTypeChoices, PartOfSpeechChoices
from words.models import UserWord, Word, WordInflection


class BotUserWordsApiTests(TestCase):
    def test_bot_can_list_only_the_telegram_users_words(self):
        user = get_user_model().objects.create_user(username="bot-word-user", telegram_id=12345)
        other_user = get_user_model().objects.create_user(username="other-word-user", telegram_id=67890)
        own_word = UserWord.objects.create(
            user=user,
            word=Word.objects.create(word="Haus", part_of_speech=PartOfSpeechChoices.NOUN),
        )
        UserWord.objects.create(
            user=other_user,
            word=Word.objects.create(word="Baum", part_of_speech=PartOfSpeechChoices.NOUN),
        )

        response = self.client.get(
            "/api/words/me",
            HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY,
            HTTP_X_TELEGRAM_ID=str(user.telegram_id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([word["id"] for word in response.json()], [own_word.pk])


class WordPagesApiTests(TestCase):
    def test_id_pages_have_fixed_size_and_report_whether_more_words_exist(self):
        Word.objects.bulk_create(
            [Word(word=f"word-{number:03d}", part_of_speech=PartOfSpeechChoices.NOUN) for number in range(205)]
        )
        expected_ids = list(Word.objects.order_by("id").values_list("id", flat=True))

        for page, expected_page_ids, has_next in [
            (1, expected_ids[:100], True),
            (2, expected_ids[100:200], True),
            (3, expected_ids[200:], False),
            (4, [], False),
        ]:
            with self.subTest(page=page):
                response = self.client.get(f"/api/words/pages/id/{page}")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual([word["id"] for word in data["words"]], expected_page_ids)
                self.assertEqual(data["page"], page)
                self.assertEqual(data["sort"], "id")
                self.assertEqual(data["page_size"], 100)
                self.assertEqual(data["has_next"], has_next)

    def test_popularity_counts_current_users_and_breaks_ties_by_word_id(self):
        first, second, third, fourth = [
            Word.objects.create(word=name, part_of_speech=PartOfSpeechChoices.NOUN)
            for name in ("first", "second", "third", "fourth")
        ]
        first_user = get_user_model().objects.create_user(username="popularity-first")
        second_user = get_user_model().objects.create_user(username="popularity-second")
        UserWord.objects.create(user=first_user, word=first)
        UserWord.objects.create(user=first_user, word=second)
        UserWord.objects.create(user=second_user, word=second)
        UserWord.objects.create(user=second_user, word=third)

        def ordered_ids():
            response = self.client.get("/api/words/pages/popular/1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["sort"], "popular")
            return [word["id"] for word in response.json()["words"]]

        self.assertEqual(ordered_ids(), [second.pk, first.pk, third.pk, fourth.pk])
        UserWord.objects.get(user=second_user, word=second).delete()
        self.assertEqual(ordered_ids(), [first.pk, second.pk, third.pk, fourth.pk])
        UserWord.objects.get(user=first_user, word=second).delete()
        self.assertEqual(ordered_ids(), [first.pk, third.pk, second.pk, fourth.pk])

    def test_page_and_sort_are_required_valid_path_components(self):
        self.assertEqual(self.client.get("/api/words/").status_code, 405)
        self.assertEqual(self.client.get("/api/words/pages/id/0").status_code, 422)
        self.assertEqual(self.client.get("/api/words/pages/unknown/1").status_code, 422)


class WordInflectionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="inflection-user")
        self.other_user = get_user_model().objects.create_user(username="inflection-other")
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"}, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHMS[0]
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.word = Word.objects.create(word="gehen", part_of_speech=PartOfSpeechChoices.VERB)
        UserWord.objects.create(user=self.user, word=self.word)
        self.url = f"/api/words/{self.word.pk}/inflections"

    def test_crud_updates_schedule_cards_and_eligibility(self):
        created = self.client.post(
            self.url,
            data={"type": InflectionTypeChoices.DE_PARTIZIP_2, "value": "  gegangen  "},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 201)
        inflection_id = created.json()["id"]
        self.assertEqual(created.json()["value"], "gegangen")
        self.assertEqual(created.json()["word_id"], self.word.pk)
        self.assertEqual([item["id"] for item in self.client.get(self.url, **self.auth).json()], [inflection_id])
        item_url = f"{self.url}/{inflection_id}"
        self.assertEqual(self.client.get(item_url, **self.auth).json()["value"], "gegangen")

        schedule = self.client.post(
            "/api/schedules/",
            data={
                "dataset_id": None,
                "mode": "interval",
                "interval_minutes": 60,
                "exercise_kind": "inflection",
                "inflection_type": InflectionTypeChoices.DE_PARTIZIP_2,
                "items_per_delivery": 1,
            },
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(schedule.status_code, 201)
        schedule_id = schedule.json()["id"]
        cards_url = f"/api/schedules/{schedule_id}/cards"
        self.assertEqual(self.client.get(cards_url, **self.auth).json()[0]["answer"], "gegangen")

        updated = self.client.patch(
            item_url, data={"value": "  gegangEN  "}, content_type="application/json", **self.auth
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["value"], "gegangEN")
        self.assertEqual(self.client.get(cards_url, **self.auth).json()[0]["answer"], "gegangEN")

        deleted = self.client.delete(item_url, **self.auth)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(self.url, **self.auth).json(), [])
        self.assertIsNone(self.client.get(cards_url, **self.auth).json()[0]["answer"])

    def test_duplicate_invalid_and_incompatible_forms_are_rejected(self):
        WordInflection.objects.create(word=self.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen")

        for data, expected_status in [
            ({"type": InflectionTypeChoices.DE_PARTIZIP_2, "value": "gegangen"}, 409),
            ({"type": "unknown", "value": "gegangen"}, 422),
            ({"type": InflectionTypeChoices.DE_PRATERITUM, "value": "   "}, 422),
            ({"type": InflectionTypeChoices.DE_PLURAL, "value": "Gänge"}, 422),
            ({"type": InflectionTypeChoices.EN_PAST_SIMPLE, "value": "went"}, 422),
        ]:
            with self.subTest(data=data):
                response = self.client.post(self.url, data=data, content_type="application/json", **self.auth)
                self.assertEqual(response.status_code, expected_status)

        self.assertEqual(WordInflection.objects.filter(word=self.word).count(), 1)

    def test_patch_rejects_conflicting_type_null_and_blank_value(self):
        first = WordInflection.objects.create(
            word=self.word, type=InflectionTypeChoices.DE_PARTIZIP_2, value="gegangen"
        )
        second = WordInflection.objects.create(word=self.word, type=InflectionTypeChoices.DE_PRATERITUM, value="ging")
        url = f"{self.url}/{second.pk}"

        for data, expected_status in [
            ({"type": first.type}, 409),
            ({"type": None}, 422),
            ({"value": None}, 422),
            ({"value": "   "}, 422),
        ]:
            with self.subTest(data=data):
                response = self.client.patch(url, data=data, content_type="application/json", **self.auth)
                self.assertEqual(response.status_code, expected_status)

        second.refresh_from_db()
        self.assertEqual((second.type, second.value), (InflectionTypeChoices.DE_PRATERITUM, "ging"))

    def test_inflections_are_available_only_for_words_in_users_vocabulary(self):
        other_word = Word.objects.create(word="Baum", part_of_speech=PartOfSpeechChoices.NOUN)
        UserWord.objects.create(user=self.other_user, word=other_word)
        other_inflection = WordInflection.objects.create(
            word=other_word, type=InflectionTypeChoices.DE_PLURAL, value="Bäume"
        )
        other_url = f"/api/words/{other_word.pk}/inflections"

        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.get(other_url, **self.auth).status_code, 404)
        self.assertEqual(
            self.client.post(
                other_url,
                data={"type": InflectionTypeChoices.DE_PLURAL, "value": "Bäume"},
                content_type="application/json",
                **self.auth,
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get(f"{other_url}/{other_inflection.pk}", **self.auth).status_code, 404)
        self.assertEqual(self.client.delete(f"{other_url}/{other_inflection.pk}", **self.auth).status_code, 404)
        self.assertTrue(WordInflection.objects.filter(pk=other_inflection.pk).exists())
