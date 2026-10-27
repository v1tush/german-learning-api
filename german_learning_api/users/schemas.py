from django.contrib.auth import get_user_model
from ninja import ModelSchema

User = get_user_model()


class UserMeOut(ModelSchema):
    class Meta:
        model = User
        fields = [
            "id",
            'username',
            'telegram_id',
            'email',
            "date_joined",
            "is_active",
            "is_staff",
            "current_using_language",
            "current_learning_language",
            "avatar"
        ]