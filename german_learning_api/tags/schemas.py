from ninja import Schema


class TagCreate(Schema):
    name: str


class TagOut(Schema):
    id: int
    name: str


class TagDetailOut(TagOut):
    weight: int


class ErrorOut(Schema):
    detail: str


class TagWordsIn(Schema):
    user_word_ids: list[int]


class TagWordsAddedOut(Schema):
    added: int
    already_in_tag: int


class TagWordsRemovedOut(Schema):
    removed: int
    not_in_tag: int


class TagWordOut(Schema):
    id: int
    word_id: int
    word: str
    language: str
    part_of_speech: str
    custom_translation: str | None
    user_hint: str | None
    status: str