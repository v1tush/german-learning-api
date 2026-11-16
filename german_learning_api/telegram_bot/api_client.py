from typing import Any

import aiohttp


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


class ApiUnavailable(Exception):
    pass


class WozziApi:
    def __init__(self, base_url: str, key: str, session: aiohttp.ClientSession):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.session = session

    async def _request(
        self, method: str, path: str, telegram_id: int, *, expected_type: type = dict, **kwargs: Any
    ) -> dict | list | None:
        headers = {"X-API-Key": self.key, "X-Telegram-ID": str(telegram_id)}
        try:
            async with self.session.request(method, f"{self.base_url}{path}", headers=headers, **kwargs) as response:
                try:
                    payload = await response.json(content_type=None)
                except aiohttp.ContentTypeError, ValueError:
                    payload = None
                if response.status >= 400:
                    detail = payload.get("detail", "api_error") if isinstance(payload, dict) else "api_error"
                    raise ApiError(response.status, str(detail))
                if not isinstance(payload, expected_type):
                    raise ApiUnavailable("unexpected_api_response")
                return payload
        except (aiohttp.ClientError, TimeoutError) as error:
            raise ApiUnavailable("api_unavailable") from error

    async def profile(self, telegram_id: int) -> dict:
        return await self._request("GET", "/users/me/", telegram_id)

    async def register(self, telegram_id: int, username: str, language: str, learning_language: str) -> dict:
        return await self._request(
            "POST",
            "/users/telegram-register",
            telegram_id,
            json={
                "username": username,
                "current_using_language": language,
                "current_learning_language": learning_language,
            },
        )

    async def confirm_link(self, telegram_id: int, token: str) -> dict:
        return await self._request("POST", "/users/telegram-link/confirm", telegram_id, json={"token": token})

    async def update_profile(self, telegram_id: int, changes: dict) -> dict:
        return await self._request("PATCH", "/users/me/", telegram_id, json=changes)

    async def upload_avatar(self, telegram_id: int, picture: bytes) -> dict:
        form = aiohttp.FormData()
        form.add_field("avatar", picture, filename="avatar.jpg", content_type="image/jpeg")
        return await self._request("POST", "/users/me/avatar", telegram_id, data=form)

    async def delete_avatar(self, telegram_id: int) -> dict:
        return await self._request("DELETE", "/users/me/avatar", telegram_id)

    async def avatar(self, telegram_id: int) -> bytes | None:
        headers = {"X-API-Key": self.key, "X-Telegram-ID": str(telegram_id)}
        try:
            async with self.session.get(f"{self.base_url}/users/me/avatar", headers=headers) as response:
                if response.status == 404:
                    return None
                if response.status >= 400:
                    raise ApiError(response.status, "avatar_unavailable")
                if not response.content_type.startswith("image/"):
                    raise ApiUnavailable("unexpected_avatar_response")
                return await response.read()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise ApiUnavailable("api_unavailable") from error

    async def user_words(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", "/words/me", telegram_id, expected_type=list)

    async def user_word(self, telegram_id: int, user_word_id: int) -> dict:
        return await self._request("GET", f"/words/me/{user_word_id}", telegram_id)

    async def delete_user_word(self, telegram_id: int, user_word_id: int) -> None:
        await self._request("DELETE", f"/words/me/{user_word_id}", telegram_id, expected_type=type(None))

    async def word(self, telegram_id: int, word_id: int) -> dict:
        return await self._request("GET", f"/words/{word_id}", telegram_id)

    async def create_word(self, telegram_id: int, word: str, language: str, part_of_speech: str) -> dict:
        return await self._request(
            "POST",
            "/words/",
            telegram_id,
            json={"word": word, "language": language, "part_of_speech": part_of_speech},
        )

    async def add_user_word(self, telegram_id: int, word_id: int, selection: dict | None = None) -> dict:
        payload = {"word_id": word_id}
        if selection is not None:
            payload["translation_selection"] = selection
        return await self._request("POST", "/words/me", telegram_id, json=payload)

    async def word_translations(self, telegram_id: int, word_id: int) -> dict:
        return await self._request("GET", f"/translations/words/{word_id}/translations", telegram_id)

    async def suggest_translations(self, telegram_id: int, word_id: int) -> dict:
        return await self._request(
            "POST",
            f"/translations/words/{word_id}/translation-suggestions",
            telegram_id,
            timeout=aiohttp.ClientTimeout(total=45),
        )

    async def word_inflections(self, telegram_id: int, word_id: int) -> list[dict]:
        return await self._request("GET", f"/words/{word_id}/inflections", telegram_id, expected_type=list)

    async def datasets(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", "/datasets/", telegram_id, expected_type=list)

    async def dataset_words(self, telegram_id: int, dataset_id: int) -> list[dict]:
        return await self._request("GET", f"/datasets/{dataset_id}/words", telegram_id, expected_type=list)

    async def dataset(self, telegram_id: int, dataset_id: int) -> dict:
        return await self._request("GET", f"/datasets/{dataset_id}", telegram_id)

    async def schedules(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", "/schedules/", telegram_id, expected_type=list)

    async def schedule(self, telegram_id: int, schedule_id: int) -> dict:
        return await self._request("GET", f"/schedules/{schedule_id}", telegram_id)
