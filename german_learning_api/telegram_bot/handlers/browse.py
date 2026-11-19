from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.api_client import WozziApi
from telegram_bot.common import reset_navigation_state
from telegram_bot.screens.datasets import show_dataset_detail, show_datasets
from telegram_bot.screens.schedules import show_schedule_detail, show_schedules
from telegram_bot.screens.words import show_word_detail, show_words

router = Router()


@router.callback_query(F.data.startswith("words:open:"))
async def open_words(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_words(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("words:translated:"))
async def open_translated_words(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_words(callback, state, api, int(callback.data.rsplit(":", 1)[-1]), only_translated=True)


@router.callback_query(F.data.startswith("words:item:"))
async def open_word_detail(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    parts = callback.data.split(":")
    _, _, user_word_id, page = parts[:4]
    only_translated = len(parts) > 4 and parts[4] == "translated"
    await reset_navigation_state(state)
    await show_word_detail(callback, state, api, int(user_word_id), int(page), only_translated=only_translated)


@router.callback_query(F.data.startswith("datasets:open:"))
async def open_datasets(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_datasets(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("datasets:item:"))
async def open_dataset_detail(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, dataset_id, page, back_page = callback.data.split(":")
    await reset_navigation_state(state)
    await show_dataset_detail(callback, state, api, int(dataset_id), int(page), int(back_page))


@router.callback_query(F.data.startswith("schedules:open:"))
async def open_schedules(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await show_schedules(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("schedules:item:"))
async def open_schedule_detail(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, schedule_id, page = callback.data.split(":")
    await show_schedule_detail(callback, state, api, int(schedule_id), int(page))
