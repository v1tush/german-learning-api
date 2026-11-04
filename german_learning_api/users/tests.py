from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

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


class TelegramOnboardingAndProfileTests(TestCase):
    def setUp(self):
        self.bot_auth = {"HTTP_X_API_KEY": settings.TG_BOT_AUTH_KEY, "HTTP_X_TELEGRAM_ID": "123456789"}

    def register(self, username="new-learner", language="ru", learning="de", **auth):
        return self.client.post(
            "/api/users/telegram-register",
            data={
                "username": username,
                "current_using_language": language,
                "current_learning_language": learning,
            },
            content_type="application/json",
            **auth,
        )

    def patch_profile(self, data, **auth):
        return self.client.patch("/api/users/me/", data=data, content_type="application/json", **auth)

    def test_bot_registration_creates_linked_user_without_site_password(self):
        response = self.register(**self.bot_auth)

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(telegram_id=123456789)
        self.assertEqual(user.username, "new-learner")
        self.assertEqual(user.current_using_language, "ru")
        self.assertEqual(user.current_learning_language, "de")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(response.json()["id"], user.pk)
        self.assertEqual(self.client.get("/api/users/me/", **self.bot_auth).status_code, 200)

    def test_registration_requires_bot_key_and_valid_telegram_id(self):
        self.assertEqual(self.register().status_code, 401)
        self.assertEqual(self.register(HTTP_X_API_KEY="wrong", HTTP_X_TELEGRAM_ID="1").status_code, 401)
        self.assertEqual(self.register(HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY).status_code, 400)
        self.assertEqual(
            self.register(HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY, HTTP_X_TELEGRAM_ID="0").status_code, 400
        )
        self.assertFalse(get_user_model().objects.filter(username="new-learner").exists())

    def test_registration_rejects_duplicate_user_and_unsupported_language(self):
        self.assertEqual(self.register(**self.bot_auth).status_code, 201)
        self.assertEqual(self.register(username="another", **self.bot_auth).status_code, 409)
        other_auth = {**self.bot_auth, "HTTP_X_TELEGRAM_ID": "987654321"}
        self.assertEqual(self.register(**other_auth).status_code, 409)
        self.assertEqual(self.register(username="ok", language="fr", **other_auth).status_code, 422)

    def test_profile_can_be_updated_by_bot_and_site_but_not_privileged_fields(self):
        self.register(**self.bot_auth)
        user = get_user_model().objects.get(telegram_id=123456789)
        token = jwt.encode(
            {"sub": str(user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        site_auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        bot_response = self.patch_profile(
            {"username": " renamed ", "current_using_language": "en", "is_staff": True, "telegram_id": 1},
            **self.bot_auth,
        )
        self.assertEqual(bot_response.status_code, 200)
        self.assertEqual(bot_response.json()["username"], "renamed")
        site_response = self.patch_profile(
            {"email": "learner@example.com", "current_learning_language": "ru"}, **site_auth
        )
        self.assertEqual(site_response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "learner@example.com")
        self.assertEqual(user.current_using_language, "en")
        self.assertEqual(user.current_learning_language, "ru")
        self.assertEqual(user.telegram_id, 123456789)
        self.assertFalse(user.is_staff)
        self.assertEqual(self.patch_profile({"username": "hacker"}).status_code, 401)

    def test_profile_rejects_invalid_fields_and_conflicts(self):
        self.register(**self.bot_auth)
        get_user_model().objects.create_user(username="taken", email="taken@example.com")

        self.assertEqual(self.patch_profile({"username": "taken"}, **self.bot_auth).status_code, 409)
        self.assertEqual(self.patch_profile({"email": "taken@example.com"}, **self.bot_auth).status_code, 409)
        self.assertEqual(self.patch_profile({"email": "bad email"}, **self.bot_auth).status_code, 422)
        self.assertEqual(self.patch_profile({"username": " "}, **self.bot_auth).status_code, 422)
        self.assertEqual(self.patch_profile({"current_using_language": None}, **self.bot_auth).status_code, 422)
        self.assertEqual(self.patch_profile({"current_learning_language": "fr"}, **self.bot_auth).status_code, 422)
        self.assertEqual(self.patch_profile({"email": None}, **self.bot_auth).status_code, 200)

    def test_avatar_is_normalized_replaced_deleted_and_invalid_image_rejected(self):
        self.register(**self.bot_auth)
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

        image = BytesIO()
        Image.new("RGB", (800, 400), "red").save(image, format="JPEG")
        uploaded = SimpleUploadedFile("picture.jpg", image.getvalue(), content_type="image/jpeg")
        response = self.client.post("/api/users/me/avatar", {"avatar": uploaded}, **self.bot_auth)
        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(telegram_id=123456789)
        self.assertTrue(user.avatar)
        with Image.open(user.avatar.path) as stored:
            self.assertEqual(stored.size, (400, 400))

        mismatch = SimpleUploadedFile("picture.png", image.getvalue(), content_type="image/png")
        self.assertEqual(
            self.client.post("/api/users/me/avatar", {"avatar": mismatch}, **self.bot_auth).status_code, 422
        )
        new_image = BytesIO()
        Image.new("RGB", (300, 600), "blue").save(new_image, format="PNG")
        replacement = SimpleUploadedFile("picture.png", new_image.getvalue(), content_type="image/png")
        old_name = user.avatar.name
        self.assertEqual(
            self.client.post("/api/users/me/avatar", {"avatar": replacement}, **self.bot_auth).status_code, 200
        )
        user.refresh_from_db()
        self.assertNotEqual(user.avatar.name, old_name)
        self.assertTrue(user.avatar.name.endswith(".png"))

        bad = SimpleUploadedFile("fake.jpg", b"not a picture", content_type="image/jpeg")
        self.assertEqual(self.client.post("/api/users/me/avatar", {"avatar": bad}, **self.bot_auth).status_code, 422)
        self.assertEqual(self.client.delete("/api/users/me/avatar", **self.bot_auth).status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.avatar)
        self.assertEqual(self.client.post("/api/users/me/avatar", {"avatar": uploaded}).status_code, 401)
