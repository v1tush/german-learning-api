from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **kwargs):
        if not username:
            raise ValueError("Users must have username")

        user = self.model(
            username=username,
            **kwargs,
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, username, password, **kwargs):
        user = self.create_user(
            username=username,
            password=password,
            is_staff=True,
            is_superuser=True,
            **kwargs,
        )

        return user
