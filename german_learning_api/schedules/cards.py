from django.db.models import Prefetch
from translations.models import BaseTranslation
from words.models import UserWordTranslation, WordInflection

from schedules.models import StudySchedule
from schedules.services import get_schedule_dataset_words


def list_schedule_cards(schedule: StudySchedule, *, user_word_id: int | None = None) -> list[dict]:
    """Return the entire dataset; the site decides which statuses to practise."""
    words = get_schedule_dataset_words(schedule)
    if user_word_id is not None:
        words = words.filter(pk=user_word_id)
    user_words = list(
        words.select_related("word")
        .prefetch_related(
            Prefetch(
                "translations",
                queryset=UserWordTranslation.objects.filter(
                    target_language=schedule.user.current_using_language
                ).select_related("base_translation"),
                to_attr="current_translations",
            )
        )
        .order_by("pk")
    )
    word_ids = {user_word.word_id for user_word in user_words}
    main_translations = {}
    inflections = {}

    if schedule.exercise_kind == StudySchedule.ExerciseKind.TRANSLATION:
        main_translations = {
            translation.word_id: translation.translation.strip()
            for translation in BaseTranslation.objects.filter(
                word_id__in=word_ids,
                target_language=schedule.user.current_using_language,
                is_main=True,
            )
        }
    else:
        inflections = {
            inflection.word_id: inflection.value
            for inflection in WordInflection.objects.filter(word_id__in=word_ids, type=schedule.inflection_type)
        }

    cards = []
    for user_word in user_words:
        answer = None
        answer_source = None
        if schedule.exercise_kind == StudySchedule.ExerciseKind.TRANSLATION:
            primary = next((row for row in user_word.current_translations if row.is_card_primary), None)
            if primary is not None:
                if primary.base_translation_id is None:
                    answer, answer_source = primary.custom_translation.strip(), "custom"
                else:
                    answer, answer_source = primary.base_translation.translation.strip(), "selected"
            elif main := main_translations.get(user_word.word_id):
                answer, answer_source = main, "main"
        elif form := inflections.get(user_word.word_id):
            answer, answer_source = form, "inflection"

        cards.append(
            {
                "id": user_word.pk,
                "word_id": user_word.word_id,
                "word": user_word.word.word,
                "language": user_word.word.language,
                "part_of_speech": user_word.word.part_of_speech,
                "status": user_word.status,
                "user_hint": user_word.user_hint,
                "answer": answer,
                "answer_source": answer_source,
            }
        )
    return cards
