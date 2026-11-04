import jwt
from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import RequestFactory, SimpleTestCase, TestCase
from schedules.models import StudySchedule
from tags.models import UserTag
from translations.choices import WordStatusChoices
from words.choices import PartOfSpeechChoices
from words.models import UserWord, Word

from datasets.admin import UserDatasetAdmin
from datasets.models import UserDataset
from datasets.services import get_dataset_words


def create_user_word(user, text: str, *, status: str = WordStatusChoices.LEARNING) -> UserWord:
    word = Word.objects.create(word=text, part_of_speech=PartOfSpeechChoices.NOUN)
    return UserWord.objects.create(user=user, word=word, status=status)


class UserDatasetServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dataset-service-user")
        self.other_user = get_user_model().objects.create_user(username="dataset-service-other")
        self.tag = UserTag.objects.create(user=self.user, name="selected")
        self.dataset = UserDataset.objects.create(user=self.user, name="My set")
        self.dataset.tags.add(self.tag)

    def test_membership_is_dynamic_and_explicit_words_survive_tag_changes(self):
        tagged_word = create_user_word(self.user, "dataset-eins")
        tagged_word.tags.add(self.tag)
        self.assertEqual(set(get_dataset_words(self.dataset)), {tagged_word})

        later_word = create_user_word(self.user, "dataset-zwei")
        later_word.tags.add(self.tag)
        self.assertEqual(set(get_dataset_words(self.dataset)), {tagged_word, later_word})

        self.dataset.extra_words.add(tagged_word)
        tagged_word.tags.remove(self.tag)
        self.assertEqual(set(get_dataset_words(self.dataset)), {tagged_word, later_word})

        self.dataset.tags.remove(self.tag)
        self.assertEqual(set(get_dataset_words(self.dataset)), {tagged_word})

    def test_union_deduplicates_and_scopes_to_owner_without_filtering_status(self):
        tagged = create_user_word(self.user, "dataset-paused", status=WordStatusChoices.PAUSED)
        tagged.tags.add(self.tag)
        extra = create_user_word(self.user, "dataset-mastered", status=WordStatusChoices.MASTERED)
        self.dataset.extra_words.add(tagged, extra)

        foreign = create_user_word(self.other_user, "dataset-foreign")
        foreign.tags.add(self.tag)

        self.assertEqual(list(get_dataset_words(self.dataset).order_by("pk")), [tagged, extra])

    def test_m2m_managers_reject_foreign_tags_in_both_directions(self):
        foreign_tag = UserTag.objects.create(user=self.other_user, name="foreign")
        foreign_dataset = UserDataset.objects.create(user=self.other_user, name="Foreign set")

        with self.assertRaises(ValidationError), transaction.atomic():
            self.dataset.tags.add(foreign_tag)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.dataset.tags.set([foreign_tag])
        with self.assertRaises(ValidationError), transaction.atomic():
            self.tag.datasets.add(foreign_dataset)

        self.assertEqual(list(self.dataset.tags.all()), [self.tag])
        self.assertFalse(foreign_dataset.tags.exists())

    def test_m2m_managers_reject_foreign_words_in_both_directions(self):
        own_word = create_user_word(self.user, "dataset-owned")
        foreign_word = create_user_word(self.other_user, "dataset-foreign-extra")
        foreign_dataset = UserDataset.objects.create(user=self.other_user, name="Foreign set")
        self.dataset.extra_words.add(own_word)

        with self.assertRaises(ValidationError), transaction.atomic():
            self.dataset.extra_words.add(foreign_word)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.dataset.extra_words.set([foreign_word])
        with self.assertRaises(ValidationError), transaction.atomic():
            own_word.datasets_as_extra.add(foreign_dataset)

        self.assertEqual(list(self.dataset.extra_words.all()), [own_word])
        self.assertFalse(foreign_dataset.extra_words.exists())


class UserDatasetAdminTests(SimpleTestCase):
    def test_owner_can_be_chosen_on_create_but_not_changed_afterward(self):
        dataset = UserDataset(user_id=1, name="Admin set")
        model_admin = UserDatasetAdmin(UserDataset, AdminSite())
        request = RequestFactory().get("/admin/datasets/userdataset/")

        self.assertNotIn("user", model_admin.get_readonly_fields(request))
        self.assertIn("user", model_admin.get_readonly_fields(request, dataset))


class UserDatasetApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dataset-api-user", telegram_id=123456)
        self.other_user = get_user_model().objects.create_user(username="dataset-api-other")
        self.tag = UserTag.objects.create(user=self.user, name="tagged")
        self.foreign_tag = UserTag.objects.create(user=self.other_user, name="foreign")
        self.tagged_word = create_user_word(self.user, "api-tagged")
        self.tagged_word.tags.add(self.tag)
        self.extra_word = create_user_word(self.user, "api-extra")
        self.foreign_word = create_user_word(self.other_user, "api-foreign")
        token = jwt.encode(
            {"sub": str(self.user.pk), "type": "access"},
            settings.JWT_SECRET_KEY,
            algorithm=settings.ALGORITHMS[0],
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_create_list_patch_and_view_effective_words(self):
        response = self.client.post(
            "/api/datasets/",
            data={"name": " My set ", "tags": [self.tag.pk], "extra_words": [self.extra_word.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        dataset_id = response.json()["id"]
        self.assertEqual(response.json()["name"], "My set")
        self.assertEqual(response.json()["tags"], [self.tag.pk])

        listed = self.client.get("/api/datasets/", **self.auth)
        detail = self.client.get(f"/api/datasets/{dataset_id}", **self.auth)
        words = self.client.get(f"/api/datasets/{dataset_id}/words", **self.auth)
        self.assertEqual([item["id"] for item in listed.json()], [dataset_id])
        self.assertEqual(detail.json()["extra_words"], [self.extra_word.pk])
        self.assertEqual({item["id"] for item in words.json()}, {self.tagged_word.pk, self.extra_word.pk})

        updated = self.client.patch(
            f"/api/datasets/{dataset_id}",
            data={"tags": []},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["tags"], [])
        words = self.client.get(f"/api/datasets/{dataset_id}/words", **self.auth)
        self.assertEqual([item["id"] for item in words.json()], [self.extra_word.pk])

        deleted = self.client.delete(f"/api/datasets/{dataset_id}", **self.auth)
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(UserDataset.objects.filter(pk=dataset_id).exists())

    def test_rejects_foreign_tags_and_words_without_partial_changes(self):
        for payload in (
            {"name": "bad tag", "tags": [self.foreign_tag.pk]},
            {"name": "bad word", "extra_words": [self.foreign_word.pk]},
        ):
            response = self.client.post("/api/datasets/", data=payload, content_type="application/json", **self.auth)
            self.assertEqual(response.status_code, 400)
        self.assertFalse(UserDataset.objects.exists())

        dataset = UserDataset.objects.create(user=self.user, name="original")
        response = self.client.patch(
            f"/api/datasets/{dataset.pk}",
            data={"name": "changed", "extra_words": [self.foreign_word.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
        dataset.refresh_from_db()
        self.assertEqual(dataset.name, "original")
        self.assertFalse(dataset.extra_words.exists())

        foreign_dataset = UserDataset.objects.create(user=self.other_user, name="other set")
        self.assertEqual(self.client.get(f"/api/datasets/{foreign_dataset.pk}", **self.auth).status_code, 404)

    def test_duplicate_name_null_relations_and_used_dataset_are_rejected(self):
        dataset = UserDataset.objects.create(user=self.user, name="existing")
        response = self.client.post(
            "/api/datasets/", data={"name": " existing "}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 409)

        for field in ("tags", "extra_words"):
            response = self.client.patch(
                f"/api/datasets/{dataset.pk}", data={field: None}, content_type="application/json", **self.auth
            )
            self.assertEqual(response.status_code, 400)

        StudySchedule.objects.create(user=self.user, dataset=dataset, interval_minutes=60)
        response = self.client.delete(f"/api/datasets/{dataset.pk}", **self.auth)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "dataset_in_use")
        self.assertTrue(UserDataset.objects.filter(pk=dataset.pk).exists())

    def test_bot_can_list_its_users_datasets(self):
        dataset = UserDataset.objects.create(user=self.user, name="bot set")
        response = self.client.get(
            "/api/datasets/",
            HTTP_X_API_KEY=settings.TG_BOT_AUTH_KEY,
            HTTP_X_TELEGRAM_ID=str(self.user.telegram_id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [dataset.pk])
