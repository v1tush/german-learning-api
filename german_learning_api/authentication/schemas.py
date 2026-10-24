from ninja import Schema


class UserIn(Schema):
    username: str
    password: str


class UserOut(Schema):
    id: int
    username: str
    access_token: str
