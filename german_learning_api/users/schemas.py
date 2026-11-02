from datetime import datetime

from django.contrib.auth import get_user_model
from ninja import ModelSchema, Schema
from pydantic import Field

User = get_user_model()


class UserMeOut(ModelSchema):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "telegram_id",
            "email",
            "date_joined",
            "is_active",
            "is_staff",
            "current_using_language",
            "current_learning_language",
            "avatar",
        ]


class TelegramLinkIssueOut(Schema):
    token: str
    expires_at: datetime


class TelegramLinkConfirmIn(Schema):
    token: str = Field(min_length=1, max_length=64)


class TelegramLinkConfirmOut(Schema):
    user_id: int
    telegram_id: int
