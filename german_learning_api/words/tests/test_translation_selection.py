import jwt
from datasets.models import UserDataset
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from tags.models import UserTag
from translations.models import BaseTranslation

from words.choices import PartOfSpeechChoices
from words.models import UserWord, UserWordTranslation, Word


class UserWordTranslationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="translation-selection-user")
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"}, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHMS[0]
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.word = Word.objects.create(word="gehen", part_of_speech=PartOfSpeechChoices.VERB)
        self.base = [
            BaseTranslation.objects.create(word=self.word, target_language="ru", translation=value)
            for value in ("идти", "ходить", "двигаться", "уходить", "направляться", "шагать")
        ]

    def request_selection(self, *, base_ids=None, primary_ids=None, custom=None, custom_primary=False):
        return {
            "base_translation_ids": base_ids if base_ids is not None else [],
            "primary_base_translation_ids": primary_ids if primary_ids is not None else [],
            "custom_translation": custom,
            "custom_is_card_primary": custom_primary,
        }

    def test_create_returns_selected_base_and_custom_translations(self):
        listed = self.client.get(f"/api/translations/words/{self.word.pk}/translations", **self.auth)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual({item["id"] for item in listed.json()["translations"]}, {item.pk for item in self.base})

        selection = self.request_selection(
            base_ids=[self.base[0].pk, self.base[1].pk],
            primary_ids=[self.base[0].pk],
            custom="  мой   вариант  ",
            custom_primary=True,
        )
        created = self.client.post(
            "/api/words/me",
            data={"word_id": self.word.pk, "translation_selection": selection},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 200, created.json())
        user_word_id = created.json()["id"]
        expected = {
            "target_language": "ru",
            "base_translations": [
                {"id": self.base[0].pk, "value": "идти", "is_card_primary": True},
                {"id": self.base[1].pk, "value": "ходить", "is_card_primary": False},
            ],
            "custom_translation": "мой вариант",
            "custom_is_card_primary": True,
        }
        self.assertEqual(created.json()["translation_selection"], expected)
        self.assertEqual(
            self.client.get(f"/api/words/me/{user_word_id}", **self.auth).json()["translation_selection"], expected
        )
        self.assertEqual(self.client.get("/api/words/me", **self.auth).json()[0]["translation_selection"], expected)
        self.assertEqual(UserWordTranslation.objects.filter(user_word_id=user_word_id).count(), 3)

    def test_patch_replaces_only_current_language_selection(self):
        user_word = UserWord.objects.create(user=self.user, word=self.word)
        ru_selection = self.request_selection(base_ids=[self.base[0].pk], primary_ids=[self.base[0].pk])
        first = self.client.patch(
            f"/api/words/me/{user_word.pk}",
            data={"translation_selection": ru_selection},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(first.status_code, 200)

        self.user.current_using_language = "en"
        self.user.save(update_fields=["current_using_language"])
        english = BaseTranslation.objects.create(word=self.word, target_language="en", translation="to go")
        en_selection = self.request_selection(base_ids=[english.pk], primary_ids=[english.pk], custom="move")
        second = self.client.patch(
            f"/api/words/me/{user_word.pk}",
            data={"translation_selection": en_selection},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["translation_selection"]["target_language"], "en")
        self.assertEqual(second.json()["translation_selection"]["custom_translation"], "move")

        self.user.current_using_language = "ru"
        self.user.save(update_fields=["current_using_language"])
        restored = self.client.get(f"/api/words/me/{user_word.pk}", **self.auth).json()["translation_selection"]
        self.assertEqual(restored["target_language"], "ru")
        self.assertEqual([item["id"] for item in restored["base_translations"]], [self.base[0].pk])
        self.assertIsNone(restored["custom_translation"])
        self.assertEqual(UserWordTranslation.objects.filter(user_word=user_word).count(), 3)

        cleared = self.client.patch(
            f"/api/words/me/{user_word.pk}",
            data={"translation_selection": {}},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["translation_selection"]["base_translations"], [])
        self.assertEqual(UserWordTranslation.objects.filter(user_word=user_word, target_language="en").count(), 2)

    def test_five_base_translations_can_be_saved_with_one_custom_translation(self):
        response = self.client.post(
            "/api/words/me",
            data={
                "word_id": self.word.pk,
                "translation_selection": self.request_selection(
                    base_ids=[item.pk for item in self.base[:5]],
                    primary_ids=[self.base[0].pk],
                    custom="свой вариант",
                    custom_primary=True,
                ),
            },
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(UserWordTranslation.objects.filter(user_word_id=response.json()["id"]).count(), 6)
        self.assertEqual(
            UserWordTranslation.objects.filter(user_word_id=response.json()["id"], is_card_primary=True).count(), 2
        )

    def test_custom_only_is_visible_in_dataset_and_tag_word_lists(self):
        created = self.client.post(
            "/api/words/me",
            data={
                "word_id": self.word.pk,
                "translation_selection": self.request_selection(custom="свой вариант", custom_primary=True),
            },
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 200)
        user_word = UserWord.objects.get(pk=created.json()["id"])
        self.assertTrue(created.json()["translation_selection"]["custom_is_card_primary"])

        tag = UserTag.objects.create(user=self.user, name="test")
        user_word.tags.add(tag)
        dataset = UserDataset.objects.create(user=self.user, name="test")
        dataset.extra_words.add(user_word)
        self.assertEqual(
            self.client.get(f"/api/tags/{tag.pk}/words", **self.auth).json()[0]["custom_translation"],
            "свой вариант",
        )
        self.assertEqual(
            self.client.get(f"/api/datasets/{dataset.pk}/words", **self.auth).json()[0]["custom_translation"],
            "свой вариант",
        )

        self.user.current_using_language = "en"
        self.user.save(update_fields=["current_using_language"])
        self.assertIsNone(
            self.client.get(f"/api/datasets/{dataset.pk}/words", **self.auth).json()[0]["custom_translation"]
        )

    def test_invalid_selection_rolls_back_other_changes(self):
        user_word = UserWord.objects.create(user=self.user, word=self.word, user_hint="old hint")
        UserWordTranslation.objects.create(
            user_word=user_word, target_language="ru", base_translation=self.base[0], is_card_primary=True
        )
        other_word = Word.objects.create(word="sehen", part_of_speech=PartOfSpeechChoices.VERB)
        wrong_word = BaseTranslation.objects.create(word=other_word, target_language="ru", translation="видеть")
        wrong_language = BaseTranslation.objects.create(word=self.word, target_language="en", translation="to go")
        invalid = [
            self.request_selection(base_ids=[item.pk for item in self.base], primary_ids=[self.base[0].pk]),
            self.request_selection(base_ids=[self.base[0].pk, self.base[0].pk], primary_ids=[self.base[0].pk]),
            self.request_selection(base_ids=[self.base[0].pk], primary_ids=[self.base[1].pk]),
            self.request_selection(base_ids=[self.base[0].pk], primary_ids=[]),
            self.request_selection(
                base_ids=[item.pk for item in self.base[:3]], primary_ids=[item.pk for item in self.base[:3]]
            ),
            self.request_selection(base_ids=[wrong_word.pk], primary_ids=[wrong_word.pk]),
            self.request_selection(base_ids=[wrong_language.pk], primary_ids=[wrong_language.pk]),
            self.request_selection(custom=" ", custom_primary=True),
            self.request_selection(base_ids=[self.base[0].pk], primary_ids=[self.base[0].pk], custom=" ИДТИ "),
        ]
        for selection in invalid:
            with self.subTest(selection=selection):
                response = self.client.patch(
                    f"/api/words/me/{user_word.pk}",
                    data={"user_hint": "new hint", "translation_selection": selection},
                    content_type="application/json",
                    **self.auth,
                )
                self.assertEqual(response.status_code, 422)
                user_word.refresh_from_db()
                self.assertEqual(user_word.user_hint, "old hint")
                self.assertEqual(
                    list(user_word.translations.values_list("base_translation_id", "is_card_primary")),
                    [(self.base[0].pk, True)],
                )

    def test_database_rejects_duplicate_or_ambiguous_rows(self):
        user_word = UserWord.objects.create(user=self.user, word=self.word)
        UserWordTranslation.objects.create(user_word=user_word, target_language="ru", base_translation=self.base[0])
        UserWordTranslation.objects.create(user_word=user_word, target_language="ru", custom_translation="свой")

        invalid_rows = [
            {"base_translation": self.base[0]},
            {"custom_translation": "ещё один"},
            {"base_translation": self.base[1], "custom_translation": "оба"},
            {},
            {"custom_translation": ""},
        ]
        for fields in invalid_rows:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                UserWordTranslation.objects.create(user_word=user_word, target_language="ru", **fields)
