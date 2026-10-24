import uuid

import jwt
from django.conf import settings
from django.utils import timezone

from authentication.models import RefreshToken

secret = settings.JWT_SECRET_KEY
algorithms = settings.ALGORITHMS


def generate_tokens(user):
    now_seconds = int(timezone.now().timestamp())

    access_data = {
        "sub": str(user.pk),
        "iat": now_seconds,
        "exp": now_seconds + 3600,  # 1 час
        "type": "access",
    }

    _uuid = uuid.uuid4()

    refresh_data = {
        "sub": str(user.pk),
        "iat": now_seconds,
        "exp": now_seconds + settings.REFRESH_TIME,
        "jti": str(_uuid),
        "type": "refresh",
    }

    access_token = jwt.encode(
        access_data,
        secret,
        algorithms if isinstance(algorithms, str) else algorithms[0],
    )

    refresh_token = jwt.encode(
        refresh_data,
        secret,
        algorithms if isinstance(algorithms, str) else algorithms[0],
    )

    RefreshToken.objects.create(
        user=user,
        token=str(_uuid),
    )

    return {
        "id": user.pk,
        "username": user.get_username(),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def set_auth_cookies(user, response):
    tokens_data = generate_tokens(user)

    response.set_cookie(
        "refresh_token",
        value=tokens_data.get("refresh_token"),
        max_age=settings.REFRESH_TIME,
        secure=not settings.DEBUG,
        httponly=True,
        samesite="Lax",
    )

    return {
        "username": user.get_username(),
        "id": user.pk,
        "access_token": tokens_data.get("access_token"),
    }
