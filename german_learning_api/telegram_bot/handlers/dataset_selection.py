from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import WozziApi
from telegram_bot.common import current_locale
from telegram_bot.screens.dataset_selection import show_dataset_tags, show_dataset_words
from telegram_bot.states import DatasetForm
from telegram_bot.texts import t

router = Router()


async def review_is_active(callback: CallbackQuery, state: FSMContext) -> bool:
    if await state.get_state() == DatasetForm.review.state:
        return True
    await callback.answer(t(await current_locale(callback, state), "stale_action"))
    return False


@router.callback_query(F.data.startswith("datasets:form:tags:"))
async def open_dataset_tags(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await review_is_active(callback, state):
        await show_dataset_tags(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("datasets:form:words:"))
async def open_dataset_words(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await review_is_active(callback, state):
        await show_dataset_words(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("datasets:form:tag:"))
async def toggle_dataset_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if not await review_is_active(callback, state):
        return
    _, _, _, tag_id, page = callback.data.split(":")
    data = await state.get_data()
    selected = set(data["dataset_tags"])
    tag_id = int(tag_id)
    if tag_id in selected:
        selected.remove(tag_id)
    else:
        selected.add(tag_id)
    await state.update_data(dataset_tags=sorted(selected))
    await show_dataset_tags(callback, state, api, int(page))


@router.callback_query(F.data.startswith("datasets:form:word:"))
async def toggle_dataset_word(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if not await review_is_active(callback, state):
        return
    _, _, _, user_word_id, page = callback.data.split(":")
    data = await state.get_data()
    selected = set(data["dataset_extra_words"])
    user_word_id = int(user_word_id)
    if user_word_id in selected:
        selected.remove(user_word_id)
    else:
        selected.add(user_word_id)
    await state.update_data(dataset_extra_words=sorted(selected))
    await show_dataset_words(callback, state, api, int(page))
