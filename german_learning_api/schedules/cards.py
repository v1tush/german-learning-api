from translations.models import BaseTranslation
from words.models import WordInflection

from schedules.models import StudySchedule
from schedules.services import get_schedule_dataset_words


def list_schedule_cards(schedule: StudySchedule, *, user_word_id: int | None = None) -> list[dict]:
    """Return the entire dataset; the site decides which statuses to practise."""
    words = get_schedule_dataset_words(schedule)
    if user_word_id is not None:
        words = words.filter(pk=user_word_id)
    user_words = list(words.select_related("word", "selected_translation").order_by("pk"))
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
            custom = (user_word.custom_translation or "").strip()
            selected = user_word.selected_translation
            selected_answer = (selected.translation or "").strip() if selected else ""
            if custom:
                answer, answer_source = custom, "custom"
            elif (
                selected
                and selected.word_id == user_word.word_id
                and selected.target_language == schedule.user.current_using_language
                and selected_answer
            ):
                answer, answer_source = selected_answer, "selected"
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
