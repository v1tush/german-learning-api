from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from users.models import TelegramLinkRequest


class TelegramLinkApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="site-user")
        self.other_user = get_user_model().objects.create_user(username="other-user")
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        self.site_auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.bot_auth = {"HTTP_X_API_KEY": settings.TG_BOT_AUTH_KEY, "HTTP_X_TELEGRAM_ID": "123456789"}

    def request_link(self, **auth):
        return self.client.post("/api/users/me/telegram-link", **auth)

    def confirm_link(self, token, **auth):
        return self.client.post(
            "/api/users/telegram-link/confirm",
            data={"token": token},
            content_type="application/json",
            **auth,
        )

    def test_site_user_can_issue_short_lived_link_token(self):
        response = self.request_link(**self.site_auth)

        self.assertEqual(response.status_code, 201)
        token = response.json()["token"]
        self.assertTrue(token)
        self.assertLessEqual(len(token), 64)
        self.assertEqual(response["Cache-Control"], "no-store")
        link = TelegramLinkRequest.objects.get(user=self.user)
        self.assertNotEqual(link.token_hash, token)
        self.assertLessEqual(link.expires_at, timezone.now() + timedelta(minutes=10))
        self.assertGreater(link.expires_at, timezone.now())
        self.assertEqual(self.request_link().status_code, 401)
        self.assertEqual(self.request_link(**self.bot_auth).status_code, 401)

    def test_bot_confirms_link_once_and_existing_bot_auth_works(self):
        token = self.request_link(**self.site_auth).json()["token"]

        response = self.confirm_link(token, **self.bot_auth)

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.telegram_id, 123456789)
        self.assertEqual(response.json()["telegram_id"], 123456789)
        self.assertFalse(TelegramLinkRequest.objects.filter(user=self.user).exists())
        self.assertEqual(self.confirm_link(token, **self.bot_auth).status_code, 400)
        self.assertEqual(self.client.get("/api/users/me/", **self.bot_auth).json()["id"], self.user.pk)

    def test_reissuing_link_invalidates_old_token(self):
        first = self.request_link(**self.site_auth).json()["token"]
        second = self.request_link(**self.site_auth).json()["token"]

        self.assertNotEqual(first, second)
        self.assertEqual(self.confirm_link(first, **self.bot_auth).status_code, 400)
        self.assertEqual(self.confirm_link(second, **self.bot_auth).status_code, 200)

    def test_expired_token_cannot_link(self):
        token = self.request_link(**self.site_auth).json()["token"]
        TelegramLinkRequest.objects.filter(user=self.user).update(expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.confirm_link(token, **self.bot_auth).status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)

    def test_confirmation_requires_bot_key_and_valid_telegram_id(self):
        token = self.request_link(**self.site_auth).json()["token"]

        self.assertEqual(self.confirm_link(token).status_code, 401)
        self.assertEqual(self.confirm_link(token, **self.site_auth).status_code, 401)
        self.assertEqual(self.confirm_link(token, HTTP_X_API_KEY="wrong", HTTP_X_TELEGRAM_ID="123").status_code, 401)
        self.assertEqual(self.confirm_link(token, HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY).status_code, 400)
        self.assertEqual(
            self.confirm_link(token, HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY, HTTP_X_TELEGRAM_ID="bad").status_code,
            400,
        )
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)

    def test_confirmation_rejects_non_user_telegram_ids(self):
        token = self.request_link(**self.site_auth).json()["token"]

        for telegram_id in ("0", "-1", "9223372036854775808"):
            with self.subTest(telegram_id=telegram_id):
                auth = {**self.bot_auth, "HTTP_X_TELEGRAM_ID": telegram_id}
                self.assertEqual(self.confirm_link(token, **auth).status_code, 400)

        self.assertEqual(self.confirm_link(token, **self.bot_auth).status_code, 200)

    def test_telegram_id_cannot_be_claimed_twice(self):
        self.other_user.telegram_id = 123456789
        self.other_user.save(update_fields=["telegram_id"])
        token = self.request_link(**self.site_auth).json()["token"]

        response = self.confirm_link(token, **self.bot_auth)

        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertTrue(TelegramLinkRequest.objects.filter(user=self.user).exists())

    def test_linked_or_inactive_user_cannot_issue_token(self):
        self.user.telegram_id = 123456789
        self.user.save(update_fields=["telegram_id"])
        self.assertEqual(self.request_link(**self.site_auth).status_code, 409)

        self.user.telegram_id = None
        self.user.is_active = False
        self.user.save(update_fields=["telegram_id", "is_active"])
        self.assertEqual(self.request_link(**self.site_auth).status_code, 403)
