from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    username = State()
    learning_language = State()
    confirmation = State()


class ProfileEdit(StatesGroup):
    username = State()
    email = State()
    email_delete_confirmation = State()
    avatar = State()
    avatar_delete_confirmation = State()
    locale = State()
    learning_language = State()


class WordAddition(StatesGroup):
    spelling = State()
    part_of_speech = State()
    translations = State()
    custom_translation = State()
    primaries = State()
    confirmation = State()


class WordDeletion(StatesGroup):
    confirmation = State()
