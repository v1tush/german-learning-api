import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from ninja.errors import HttpError
from ninja.security import APIKeyCookie, APIKeyHeader, HttpBearer

secret_jwt = settings.JWT_SECRET_KEY
secret_tg = settings.TG_BOT_AUTH_KEY
algorithms = settings.ALGORITHMS

User = get_user_model()


def validate_and_decode_token(token: str, secret: str | None = None, algorithms: list | None = None) -> dict:
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
    def authenticate(self, request: HttpRequest, token: str) -> User | None:

        decoded = validate_and_decode_token(token)

        if decoded.get("type") != "access":
            raise HttpError(401, "invalid_token_type")

        try:
            user = User.objects.get(id=int(decoded.get("sub")))
        except ValueError, TypeError:
            raise HttpError(401, "invalid_token_payload")
        except ObjectDoesNotExist:
            raise HttpError(401, "user_does_not_exist")
        return user


class CookieRefreshAuth(APIKeyCookie):
    param_name: str = "refresh_token"

    def authenticate(self, request: HttpRequest, key: str | None) -> dict | None:
        if not key:
            raise HttpError(401, "token_does_not_exist")

        decoded = validate_and_decode_token(key)

        if decoded.get("type") != "refresh":
            raise HttpError(401, "invalid_token_type")

        return decoded


class BotAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request: HttpRequest, key: str | None) -> User | None:
        if not key:
            return None

        if key != secret_tg:
            raise HttpError(401, "token_is_wrong")

        tg_id = request.headers.get("X-Telegram-ID")
        if not tg_id:
            raise HttpError(400, "missing_header")

        try:
            return User.objects.get(telegram_id=tg_id)
        except ValueError, TypeError, User.DoesNotExist:
            raise HttpError(404, "user_does_not_exist")
