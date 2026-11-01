from unittest.mock import patch

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from words.choices import PartOfSpeechChoices
from words.models import Word

from translations.models import BaseTranslation
from translations.schemas import Translation, TranslationResponse


class TranslationSuggestionsApiTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="translation-user")
        token = jwt.encode(
            {"sub": str(user.pk), "type": "access"}, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHMS[0]
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.word = Word.objects.create(word="gehen", part_of_speech=PartOfSpeechChoices.VERB)
        self.url = f"/api/translations/words/{self.word.pk}/translation-suggestions"

    def test_existing_non_main_translation_does_not_skip_generation(self):
        BaseTranslation.objects.create(word=self.word, target_language="ru", translation="идти", is_main=False)
        ai_result = TranslationResponse(
            word="gehen",
            part_of_speech="verb",
            status="success",
            translations=[Translation(value="идти", is_main=True), Translation(value="ходить", is_main=False)],
        )

        with patch("translations.services.get_translation", return_value=ai_result) as generate:
            first = self.client.post(self.url, **self.auth)
            second = self.client.post(self.url, **self.auth)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["translations"], second.json()["translations"])
        self.assertEqual(
            {(item["value"], item["is_main"]) for item in first.json()["translations"]},
            {("идти", True), ("ходить", False)},
        )
        generate.assert_called_once_with(self.word, "ru")
        self.assertEqual(BaseTranslation.objects.filter(word=self.word, target_language="ru").count(), 2)

    def test_existing_main_is_reused_without_ai(self):
        BaseTranslation.objects.create(word=self.word, target_language="ru", translation="идти", is_main=True)
        with patch("translations.services.get_translation") as generate:
            response = self.client.post(self.url, **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["translations"], [{"value": "идти", "is_main": True}])
        generate.assert_not_called()

    def test_normalized_existing_variant_is_promoted_without_creating_a_duplicate(self):
        existing = BaseTranslation.objects.create(
            word=self.word, target_language="ru", translation="  ПОЙТИ   ", is_main=False
        )
        ai_result = TranslationResponse(
            word="gehen",
            part_of_speech="verb",
            status="success",
            translations=[
                Translation(value="пои\u0306ти", is_main=False),
                Translation(value="пойти", is_main=True),
            ],
        )

        with patch("translations.services.get_translation", return_value=ai_result):
            response = self.client.post(self.url, **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BaseTranslation.objects.filter(word=self.word, target_language="ru").count(), 1)
        existing.refresh_from_db()
        self.assertTrue(existing.is_main)

    def test_untranslatable_word_keeps_existing_variants_without_main(self):
        BaseTranslation.objects.create(word=self.word, target_language="ru", translation="ходить", is_main=False)
        ai_result = TranslationResponse(word="gehen", part_of_speech="verb", status="not_found", translations=[])
        with patch("translations.services.get_translation", return_value=ai_result):
            response = self.client.post(self.url, **self.auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_found")
        self.assertEqual(response.json()["translations"], [{"value": "ходить", "is_main": False}])
        self.assertFalse(BaseTranslation.objects.filter(word=self.word, target_language="ru", is_main=True).exists())

    def test_provider_failure_returns_bad_gateway_without_saving(self):
        with (
            patch("translations.services.get_translation", side_effect=RuntimeError("provider unavailable")),
            patch("translations.api.logger.exception"),
        ):
            response = self.client.post(self.url, **self.auth)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "translation_unavailable")
        self.assertFalse(BaseTranslation.objects.filter(word=self.word).exists())
