from authentication.auth import BotAuth, GlobalAuth
from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError
from ninja import Router
from ninja.errors import HttpError

from datasets.models import UserDataset
from datasets.schemas import DatasetCreateIn, DatasetOut, DatasetUpdateIn, DatasetWordOut, ErrorOut
from datasets.services import (
    get_dataset_words,
    get_owned_extra_words,
    get_owned_tags,
    get_user_dataset,
    validate_dataset_name,
)

datasets_router = Router(auth=[GlobalAuth(), BotAuth()])


def serialize_dataset(dataset: UserDataset) -> dict:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "tags": sorted(tag.id for tag in dataset.tags.all()),
        "extra_words": sorted(word.id for word in dataset.extra_words.all()),
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
    }


def serialize_dataset_word(user_word) -> dict:
    return {
        "id": user_word.id,
        "word_id": user_word.word_id,
        "word": user_word.word.word,
        "language": user_word.word.language,
        "part_of_speech": user_word.word.part_of_speech,
        "custom_translation": user_word.custom_translation,
        "user_hint": user_word.user_hint,
        "status": user_word.status,
    }


@datasets_router.post("/", response={201: DatasetOut, 400: ErrorOut, 409: ErrorOut})
def create_dataset(request, data: DatasetCreateIn):
    name = validate_dataset_name(data.name)
    tags = get_owned_tags(request.auth, data.tags)
    extra_words = get_owned_extra_words(request.auth, data.extra_words)

    try:
        with transaction.atomic():
            dataset = UserDataset.objects.create(user=request.auth, name=name)
            dataset.tags.set(tags)
            dataset.extra_words.set(extra_words)
    except IntegrityError as exc:
        if UserDataset.objects.filter(user=request.auth, name=name).exists():
            raise HttpError(409, "dataset_already_exists") from exc
        raise

    return 201, serialize_dataset(dataset)


@datasets_router.get("/", response=list[DatasetOut])
def list_datasets(request):
    datasets = (
        UserDataset.objects.filter(user=request.auth).prefetch_related("tags", "extra_words").order_by("name", "id")
    )
    return [serialize_dataset(dataset) for dataset in datasets]


@datasets_router.get("/{dataset_id}", response={200: DatasetOut, 404: ErrorOut})
def get_dataset(request, dataset_id: int):
    return serialize_dataset(get_user_dataset(request.auth, dataset_id))


@datasets_router.get("/{dataset_id}/words", response={200: list[DatasetWordOut], 404: ErrorOut})
def list_dataset_words(request, dataset_id: int):
    dataset = get_user_dataset(request.auth, dataset_id)
    words = get_dataset_words(dataset).select_related("word").order_by("id")
    return [serialize_dataset_word(word) for word in words]


@datasets_router.patch("/{dataset_id}", response={200: DatasetOut, 400: ErrorOut, 404: ErrorOut, 409: ErrorOut})
def update_dataset(request, dataset_id: int, data: DatasetUpdateIn):
    payload = data.model_dump(exclude_unset=True)
    for field in ("name", "tags", "extra_words"):
        if field in payload and payload[field] is None:
            raise HttpError(400, f"{field}_cannot_be_null")

    dataset = get_user_dataset(request.auth, dataset_id)
    name = validate_dataset_name(payload["name"]) if "name" in payload else None
    tags = get_owned_tags(request.auth, payload["tags"]) if "tags" in payload else None
    extra_words = get_owned_extra_words(request.auth, payload["extra_words"]) if "extra_words" in payload else None

    try:
        with transaction.atomic():
            if name is not None:
                dataset.name = name
            if payload:
                dataset.save(update_fields=["name", "updated_at"] if name is not None else ["updated_at"])
            if tags is not None:
                dataset.tags.set(tags)
            if extra_words is not None:
                dataset.extra_words.set(extra_words)
    except IntegrityError as exc:
        if (
            name is not None
            and UserDataset.objects.filter(user=request.auth, name=name).exclude(pk=dataset.pk).exists()
        ):
            raise HttpError(409, "dataset_already_exists") from exc
        raise

    return serialize_dataset(dataset)


@datasets_router.delete("/{dataset_id}", response={204: None, 404: ErrorOut, 409: ErrorOut})
def delete_dataset(request, dataset_id: int):
    dataset = get_user_dataset(request.auth, dataset_id)
    try:
        with transaction.atomic():
            dataset.delete()
    except RestrictedError as exc:
        raise HttpError(409, "dataset_in_use") from exc
    return 204, None
