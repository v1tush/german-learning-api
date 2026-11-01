from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from tags.models import UserTag
from words.models import UserWord

from datasets.models import UserDataset


def get_user_dataset(user, dataset_id: int) -> UserDataset:
    """Return a user's dataset or raise Http404 when it is absent or belongs to another user."""
    return get_object_or_404(
        UserDataset.objects.prefetch_related("tags", "extra_words"),
        pk=dataset_id,
        user=user,
    )


def get_owned_tags(user, tag_ids: list[int]) -> list[UserTag]:
    unique_ids = set(tag_ids)
    tags = list(UserTag.objects.filter(user=user, pk__in=unique_ids))
    if len(tags) != len(unique_ids):
        raise HttpError(400, "invalid_tag_ids")
    return tags


def get_owned_extra_words(user, user_word_ids: list[int]) -> list[UserWord]:
    unique_ids = set(user_word_ids)
    words = list(UserWord.objects.filter(user=user, pk__in=unique_ids))
    if len(words) != len(unique_ids):
        raise HttpError(400, "invalid_extra_word_ids")
    return words


def get_dataset_words(dataset: UserDataset) -> QuerySet[UserWord]:
    """Resolve tag membership at query time and include explicitly selected words."""
    return (
        UserWord.objects.filter(user_id=dataset.user_id)
        .filter(Q(tags__in=dataset.tags.all()) | Q(pk__in=dataset.extra_words.values("pk")))
        .distinct()
    )


def validate_dataset_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise HttpError(400, "dataset_name_cannot_be_empty")
    if len(name) > 100:
        raise HttpError(400, "dataset_name_too_long")
    return name
