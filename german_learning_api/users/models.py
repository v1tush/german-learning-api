from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.templatetags.static import static
from django.utils import timezone

from users.managers import UserManager


def user_avatar_path(instance, filename):
    return f"users/avatars/{instance.pk}/{filename}"


class User(AbstractBaseUser, PermissionsMixin):
    class Languages(models.TextChoices):
        GERMAN = "de", "German"
        ENGLISH = "en", "English"
        RUSSIAN = "ru", "Russian"

    username = models.CharField(max_length=30, unique=True)
    telegram_id = models.BigIntegerField(unique=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    current_using_language = models.CharField(max_length=2, choices=Languages, default=Languages.RUSSIAN)
    current_learning_language = models.CharField(max_length=2, choices=Languages, default=Languages.GERMAN)
    avatar = models.ImageField(upload_to=user_avatar_path, blank=True, null=True)

    USERNAME_FIELD = "username"

    def __str__(self):
        return f"User: {self.username}"

    objects = UserManager()

    @property
    def avatar_url(self):
        if not self.avatar:
            return static("defaults/default_avatar.jpg")
        return self.avatar.url

    @property
    def is_new_user(self):
        return (timezone.now() - self.date_joined) < timedelta(days=1)
