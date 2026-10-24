from typing import Optional, Any

import jwt
from django.http import HttpRequest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from ninja.errors import HttpError
from ninja.security import HttpBearer, APIKeyCookie

secret = settings.JWT_SECRET_KEY
algorithms = settings.ALGORITHMS

User = get_user_model()


def validate_and_decode_token(
    token: str, secret: str = None, algorithms: list = None
) -> dict:
    secret = secret or settings.JWT_SECRET_KEY
    algorithms = algorithms or settings.ALGORITHMS

    try:
        data = jwt.decode(token, key=secret, algorithms=algorithms)
    except jwt.ExpiredSignatureError:
        raise HttpError(401, "token_expired")
    except jwt.InvalidSignatureError:
        raise HttpError(401, "invalid_signature")
    except jwt.DecodeError:
        raise HttpError(401, "malformed_token")
    except jwt.PyJWTError:
        raise HttpError(401, "invalid_token")

    return data


class GlobalAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Optional[User]:

        decoded = validate_and_decode_token(token)

        if decoded.get("type") != "access":
            raise HttpError(401, "invalid_token_type")

        try:
            user = User.objects.get(id=int(decoded.get("sub")))
        except (ValueError, TypeError):
            raise HttpError(401, "invalid_token_payload")
        except ObjectDoesNotExist:
            raise HttpError(401, "user_does_not_exist")
        return user


class CookieRefreshAuth(APIKeyCookie):
    param_name: str = "refresh_token"

    def authenticate(self, request: HttpRequest, key: Optional[str]) -> Optional[dict]:
        if not key:
            raise HttpError(401, "token_does_not_exist")

        decoded = validate_and_decode_token(key)

        if decoded.get("type") != "refresh":
            raise HttpError(401, "invalid_token_type")

        return decoded
