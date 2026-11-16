from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from telegram_bot.api_client import WozziApi


class ApiClientTests(IsolatedAsyncioTestCase):
    async def test_list_response_and_authenticated_avatar_download(self):
        response = SimpleNamespace(
            status=200,
            content_type="application/json",
            json=AsyncMock(return_value=[{"id": 1, "word_id": 5}]),
            read=AsyncMock(return_value=b"photo"),
        )
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = SimpleNamespace(request=Mock(return_value=context), get=Mock(return_value=context))
        api = WozziApi("http://web:8000/api", "secret", session)

        self.assertEqual(await api.user_words(42), [{"id": 1, "word_id": 5}])
        session.request.assert_called_once_with(
            "GET",
            "http://web:8000/api/words/me",
            headers={"X-API-Key": "secret", "X-Telegram-ID": "42"},
        )

        response.content_type = "image/jpeg"
        self.assertEqual(await api.avatar(42), b"photo")
        session.get.assert_called_once_with(
            "http://web:8000/api/users/me/avatar",
            headers={"X-API-Key": "secret", "X-Telegram-ID": "42"},
        )

    async def test_word_creation_and_personal_selection_use_existing_api(self):
        response = SimpleNamespace(status=200, json=AsyncMock(return_value={"id": 9}))
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = SimpleNamespace(request=Mock(return_value=context))
        api = WozziApi("http://web:8000/api", "secret", session)
        headers = {"X-API-Key": "secret", "X-Telegram-ID": "42"}

        self.assertEqual(await api.create_word(42, "Haus", "de", "noun"), {"id": 9})
        session.request.assert_called_with(
            "POST",
            "http://web:8000/api/words/",
            headers=headers,
            json={"word": "Haus", "language": "de", "part_of_speech": "noun"},
        )

        selection = {
            "base_translation_ids": [10],
            "primary_base_translation_ids": [10],
            "custom_translation": "здание",
            "custom_is_card_primary": False,
        }
        await api.add_user_word(42, 9, selection)
        session.request.assert_called_with(
            "POST",
            "http://web:8000/api/words/me",
            headers=headers,
            json={"word_id": 9, "translation_selection": selection},
        )

    async def test_delete_user_word_accepts_empty_response(self):
        response = SimpleNamespace(status=204, json=AsyncMock(return_value=None))
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = SimpleNamespace(request=Mock(return_value=context))
        api = WozziApi("http://web:8000/api", "secret", session)

        self.assertIsNone(await api.delete_user_word(42, 9))
        session.request.assert_called_once_with(
            "DELETE",
            "http://web:8000/api/words/me/9",
            headers={"X-API-Key": "secret", "X-Telegram-ID": "42"},
        )
