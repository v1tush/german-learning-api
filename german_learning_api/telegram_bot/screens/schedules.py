from datetime import UTC, datetime
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from telegram_bot.api_client import ApiError, ApiUnavailable, WozziApi
from telegram_bot.common import current_locale, keyboard, page_navigation, page_of, show
from telegram_bot.texts import t


def next_run_label(locale: str, value: str | None) -> str:
    if not value:
        return t(locale, "no_run")
    try:
        instant = datetime.fromisoformat(value)
        return instant.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
    except ValueError:
        return escape(value)


async def show_schedules(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, requested_page: int
) -> None:
    locale = await current_locale(target, state)
    try:
        schedules = sorted(await api.schedules(target.from_user.id), key=lambda item: item["id"])
    except ApiError, ApiUnavailable:
        await show(target, t(locale, "service_error"), keyboard([[(t(locale, "main_menu_button"), "menu:open")]]))
        return
    items, page, pages = page_of(schedules, requested_page)
    rows = [
        [
            (
                t(locale, "schedule_item", number=str(item["id"]), status="🟢" if item["is_enabled"] else "⚪"),
                f"schedules:item:{item['id']}:{page}",
            )
        ]
        for item in items
    ]
    rows += page_navigation("schedules:open", page, pages)
    rows.append([(t(locale, "main_menu_button"), "menu:open")])
    body = t(locale, "schedules_title", count=str(len(schedules)), page=str(page + 1), pages=str(pages))
    if not schedules:
        body += f"\n\n{t(locale, 'schedules_empty')}"
    await show(target, body, keyboard(rows))


async def show_schedule_detail(
    target: Message | CallbackQuery, state: FSMContext, api: WozziApi, schedule_id: int, page: int
) -> None:
    locale = await current_locale(target, state)
    try:
        schedule = await api.schedule(target.from_user.id, schedule_id)
    except ApiError, ApiUnavailable:
        await show_schedules(target, state, api, page)
        return
    body = t(
        locale,
        "schedule_detail",
        number=str(schedule["id"]),
        status=t(locale, "enabled" if schedule["is_enabled"] else "disabled"),
        mode=t(locale, "mode_" + schedule["mode"]),
        kind=t(locale, "kind_" + schedule["exercise_kind"]),
        count=str(schedule["items_per_delivery"]),
        next_run=next_run_label(locale, schedule.get("next_run_at")),
    )
    await show(
        target,
        body,
        keyboard(
            [
                [(t(locale, "back_to_schedules"), f"schedules:open:{page}")],
                [(t(locale, "main_menu_button"), "menu:open")],
            ]
        ),
    )
