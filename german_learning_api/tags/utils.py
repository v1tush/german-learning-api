from ninja.errors import HttpError

from tags.models import UserTag
from words.models import UserWord


def get_user_tag(request, tag_id: int) -> UserTag:
    tag = UserTag.objects.filter(
        id=tag_id,
        user=request.auth,
    ).first()

    if tag is None:
        raise HttpError(404, "tag_not_found")

    return tag


def serialize_user_word(user_word: UserWord) -> dict:
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


def get_user_words(request, user_word_ids: set[int]) -> list[UserWord]:
    user_words = list(
        UserWord.objects.filter(
            user=request.auth,
            id__in=user_word_ids,
        )
    )

    found_ids = {user_word.id for user_word in user_words}

    if found_ids != user_word_ids:
        raise HttpError(404, "user_words_not_found")

    return user_words


def validate_user_word_ids(user_word_ids: set[int]) -> None:
    if not user_word_ids:
        raise HttpError(400, "user_word_ids_required")

