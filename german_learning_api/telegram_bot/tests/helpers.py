from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from telegram_bot.api_client import ApiError
from telegram_bot.handlers import (
    browse,
    dataset_deletion,
    dataset_form,
    dataset_selection,
    fallback,
    navigation,
    onboarding,
    profile,
    profile_avatar,
    profile_text,
    tag_membership,
    tags,
    word_addition,
    word_deletion,
    word_primary,
    word_translations,
)
from telegram_bot.screens import (
    dataset_editor,
    datasets,
    menu,
    schedules,
    words,
)
from telegram_bot.screens import (
    dataset_selection as dataset_selection_screen,
)
from telegram_bot.screens import onboarding as onboarding_screen
from telegram_bot.screens import profile as profile_screen
from telegram_bot.screens import tag_membership as tag_membership_screen
from telegram_bot.screens import tags as tags_screen
from telegram_bot.screens import word_addition as word_addition_screen
from telegram_bot.screens import word_deletion as word_deletion_screen


def update(language="ru", data=None):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=42, language_code=language), data=data, text=data, answer=AsyncMock()
    )


def user_profile(language="ru"):
    return {
        "id": 7,
        "username": "learner",
        "email": None,
        "current_using_language": language,
        "current_learning_language": "de",
        "avatar": None,
    }


class BotFlowTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MemoryStorage()
        self.state = FSMContext(storage=self.storage, key=StorageKey(bot_id=1, chat_id=42, user_id=42))
        self.api = SimpleNamespace(
            profile=AsyncMock(side_effect=ApiError(404, "user_does_not_exist")),
            register=AsyncMock(return_value=user_profile()),
            confirm_link=AsyncMock(return_value={"user_id": 1, "telegram_id": 42}),
            update_profile=AsyncMock(return_value=user_profile("de")),
            avatar=AsyncMock(return_value=None),
            user_words=AsyncMock(return_value=[]),
            user_word=AsyncMock(),
            word=AsyncMock(),
            create_word=AsyncMock(),
            add_user_word=AsyncMock(),
            delete_user_word=AsyncMock(),
            word_translations=AsyncMock(return_value={"translations": []}),
            suggest_translations=AsyncMock(return_value={"status": "not_found", "translations": []}),
            word_inflections=AsyncMock(return_value=[]),
            tags=AsyncMock(return_value=[]),
            tag=AsyncMock(),
            tag_words=AsyncMock(return_value=[]),
            create_tag=AsyncMock(),
            delete_tag=AsyncMock(),
            add_tag_word=AsyncMock(),
            remove_tag_word=AsyncMock(),
            datasets=AsyncMock(return_value=[]),
            dataset=AsyncMock(),
            dataset_words=AsyncMock(return_value=[]),
            create_dataset=AsyncMock(),
            update_dataset=AsyncMock(),
            delete_dataset=AsyncMock(),
            schedules=AsyncMock(return_value=[]),
            schedule=AsyncMock(),
        )
        self.show = AsyncMock()
        self.show_photo = AsyncMock()
        self.patches = []
        modules = (
            browse,
            dataset_deletion,
            dataset_form,
            dataset_selection,
            fallback,
            navigation,
            onboarding,
            profile,
            profile_avatar,
            profile_text,
            tag_membership,
            tags,
            word_addition,
            word_deletion,
            word_primary,
            word_translations,
            datasets,
            dataset_editor,
            dataset_selection_screen,
            menu,
            onboarding_screen,
            profile_screen,
            schedules,
            tag_membership_screen,
            tags_screen,
            words,
            word_addition_screen,
            word_deletion_screen,
        )
        for module in modules:
            if "show" in vars(module):
                self.patches.append(patch.object(module, "show", self.show))
        self.patches.append(patch.object(profile_screen, "show_photo", self.show_photo))
        for active_patch in self.patches:
            active_patch.start()

    async def asyncTearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        await self.storage.close()

    def shown_buttons(self):
        return self.show.call_args.args[2].inline_keyboard

    def shown_photo_buttons(self):
        return self.show_photo.call_args.args[3].inline_keyboard
