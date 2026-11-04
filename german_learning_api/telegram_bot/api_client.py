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

    async def _request(self, method: str, path: str, telegram_id: int, **kwargs: Any) -> dict:
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
                if not isinstance(payload, dict):
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
