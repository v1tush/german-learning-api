from ninja import Schema


class Translation(Schema):
    value: str
    is_main: bool


class BaseTranslationsResponse(Schema):
    word: str
    part_of_speech: str
    translations: list[Translation]


class TranslationsListResponse(BaseTranslationsResponse):
    pass


class TranslationResponse(BaseTranslationsResponse):
    status: str
