from ninja import Schema


class Translation(Schema):
    value: str
    is_main: bool


class TranslationResponse(Schema):
    word: str
    part_of_speech: str
    status: str
    translations: list[Translation]


class SavedTranslation(Schema):
    id: int
    value: str
    is_main: bool


class TranslationsListResponse(Schema):
    word: str
    part_of_speech: str
    translations: list[SavedTranslation]


class TranslationSuggestionsResponse(TranslationsListResponse):
    status: str
