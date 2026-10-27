from ninja import Schema
from pydantic import Field


class UserIn(Schema):
    username: str = Field(..., max_length=30)
    password: str


class UserOut(Schema):
    id: int
    username: str
    access_token: str
