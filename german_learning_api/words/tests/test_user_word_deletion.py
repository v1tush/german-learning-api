from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from translations.models import BaseTranslation

from words.choices import PartOfSpeechChoices
from words.models import UserWord, UserWordTranslation, Word


class UserWordDeletionApiTests(TestCase):
    def test_bot_deletes_only_its_users_personal_entry(self):
        own_user = get_user_model().objects.create_user(username="delete-own", telegram_id=12345)
        other_user = get_user_model().objects.create_user(username="delete-other", telegram_id=67890)
        word = Word.objects.create(word="Haus", part_of_speech=PartOfSpeechChoices.NOUN)
        translation = BaseTranslation.objects.create(word=word, target_language="ru", translation="дом", is_main=True)
        own_entry = UserWord.objects.create(user=own_user, word=word)
        other_entry = UserWord.objects.create(user=other_user, word=word)
        own_selection = UserWordTranslation.objects.create(
            user_word=own_entry, target_language="ru", base_translation=translation, is_card_primary=True
        )
        other_selection = UserWordTranslation.objects.create(
            user_word=other_entry, target_language="ru", base_translation=translation, is_card_primary=True
        )
        url = f"/api/words/me/{own_entry.pk}"
        other_auth = {"HTTP_X_API_KEY": settings.TG_BOT_AUTH_KEY, "HTTP_X_TELEGRAM_ID": "67890"}
        own_auth = {"HTTP_X_API_KEY": settings.TG_BOT_AUTH_KEY, "HTTP_X_TELEGRAM_ID": "12345"}

        self.assertEqual(self.client.delete(url, **other_auth).status_code, 404)
        self.assertEqual(self.client.delete(url, **own_auth).status_code, 204)

        self.assertFalse(UserWord.objects.filter(pk=own_entry.pk).exists())
        self.assertFalse(UserWordTranslation.objects.filter(pk=own_selection.pk).exists())
        self.assertTrue(UserWord.objects.filter(pk=other_entry.pk).exists())
        self.assertTrue(UserWordTranslation.objects.filter(pk=other_selection.pk).exists())
        self.assertTrue(Word.objects.filter(pk=word.pk).exists())
        self.assertTrue(BaseTranslation.objects.filter(pk=translation.pk).exists())
