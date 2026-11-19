from html import escape

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, reset_navigation_state, show
from telegram_bot.screens.tag_membership import show_word_tag_picker
from telegram_bot.screens.tags import show_tag_detail, show_tags
from telegram_bot.states import TagCreation, TagDeletion
from telegram_bot.texts import t

router = Router()


@router.callback_query(F.data.startswith("tags:open:"))
async def open_tags(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    await reset_navigation_state(state)
    await show_tags(callback, state, api, int(callback.data.rsplit(":", 1)[-1]))


@router.callback_query(F.data.startswith("tags:item:"))
async def open_tag_detail(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, tag_id, page, back_page = callback.data.split(":")
    await reset_navigation_state(state)
    await show_tag_detail(callback, state, api, int(tag_id), int(page), int(back_page))


async def return_from_creation(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, data: dict, notice: str = ""
) -> None:
    if data.get("tag_origin") == "word":
        await show_word_tag_picker(
            target,
            state,
            api,
            data["tag_user_word_id"],
            data["tag_word_page"],
            data["tag_mode"],
            data["tag_page"],
            notice,
        )
    else:
        await show_tags(target, state, api, data.get("tag_page", 0), notice)


@router.callback_query(F.data == "tags:create:cancel")
async def cancel_create_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != TagCreation.name.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    await reset_navigation_state(state)
    await return_from_creation(callback, state, api, data)


@router.callback_query(F.data.startswith("tags:create:"))
async def start_create_tag(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    origin = parts[2]
    if origin not in {"list", "word"}:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    await reset_navigation_state(state)
    if origin == "word":
        _, _, _, user_word_id, word_page, mode, tag_page = parts
        await state.update_data(
            tag_origin="word",
            tag_user_word_id=int(user_word_id),
            tag_word_page=int(word_page),
            tag_mode=mode,
            tag_page=int(tag_page),
        )
    else:
        await state.update_data(tag_origin="list", tag_page=int(parts[3]))
    await state.set_state(TagCreation.name)
    locale = await current_locale(callback, state)
    await show(callback, t(locale, "tag_name_prompt"), keyboard([[(t(locale, "cancel"), "tags:create:cancel")]]))


@router.message(TagCreation.name)
async def receive_tag_name(message: Message, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(message, state)
    name = (message.text or "").strip()
    if not name or len(name) > 50:
        key = "tag_name_empty" if not name else "tag_name_too_long"
        await show(
            message,
            f"{t(locale, key)}\n\n{t(locale, 'tag_name_prompt')}",
            keyboard([[(t(locale, "cancel"), "tags:create:cancel")]]),
        )
        return
    try:
        tag = await api.create_tag(message.from_user.id, name)
    except ApiError as error:
        key = "tag_exists" if error.status == 409 else "service_error"
        await show(message, t(locale, key), keyboard([[(t(locale, "cancel"), "tags:create:cancel")]]))
        return
    except ApiUnavailable:
        await show(message, t(locale, "service_error"), keyboard([[(t(locale, "cancel"), "tags:create:cancel")]]))
        return
    data = await state.get_data()
    await reset_navigation_state(state)
    if data.get("tag_origin") == "word":
        try:
            await api.add_tag_word(message.from_user.id, tag["id"], data["tag_user_word_id"])
        except ApiError, ApiUnavailable:
            notice = t(locale, "tag_created_unlinked")
        else:
            notice = t(locale, "tag_created_and_added")
    else:
        notice = t(locale, "tag_created")
    if data.get("tag_origin") == "word":
        await return_from_creation(message, state, api, data, notice)
    else:
        await show_tag_detail(message, state, api, tag["id"], 0, data["tag_page"], notice)


@router.callback_query(F.data.startswith("tags:delete:ask:"))
async def ask_delete_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    _, _, _, tag_id, page, back_page = callback.data.split(":")
    locale = await current_locale(callback, state)
    try:
        tag = await api.tag(callback.from_user.id, int(tag_id))
    except ApiError, ApiUnavailable:
        await show_tags(callback, state, api, int(back_page))
        return
    await reset_navigation_state(state)
    await state.update_data(tag_id=int(tag_id), tag_detail_page=int(page), tag_page=int(back_page))
    await state.set_state(TagDeletion.confirmation)
    await show(
        callback,
        t(locale, "tag_delete_confirm", name=escape(tag["name"])),
        keyboard(
            [
                [(t(locale, "delete"), "tags:delete:confirm", ButtonStyle.DANGER)],
                [(t(locale, "cancel"), "tags:delete:cancel")],
            ]
        ),
    )


@router.callback_query(F.data == "tags:delete:cancel")
async def cancel_delete_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    if await state.get_state() != TagDeletion.confirmation.state:
        await callback.answer(t(await current_locale(callback, state), "stale_action"))
        return
    data = await state.get_data()
    await reset_navigation_state(state)
    await show_tag_detail(callback, state, api, data["tag_id"], data["tag_detail_page"], data["tag_page"])


@router.callback_query(F.data == "tags:delete:confirm")
async def delete_tag(callback: CallbackQuery, state: FSMContext, api: WozziApi) -> None:
    locale = await current_locale(callback, state)
    if await state.get_state() != TagDeletion.confirmation.state:
        await callback.answer(t(locale, "stale_action"))
        return
    data = await state.get_data()
    try:
        await api.delete_tag(callback.from_user.id, data["tag_id"])
    except ApiError, ApiUnavailable:
        await callback.answer(t(locale, "service_error"), show_alert=True)
        return
    await reset_navigation_state(state)
    await show_tags(callback, state, api, data["tag_page"], t(locale, "tag_deleted"))
