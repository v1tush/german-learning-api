from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word


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
