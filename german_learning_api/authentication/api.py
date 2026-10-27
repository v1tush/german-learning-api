from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from ninja import Router
from ninja.errors import HttpError

from authentication.auth import CookieRefreshAuth
from authentication.models import RefreshToken
from authentication.schemas import UserIn, UserOut
from authentication.utils import set_auth_cookies

authentication_router = Router()

User = get_user_model()


@authentication_router.post("/login", response=UserOut)
def login(request, response: HttpResponse, data: UserIn):
    user = authenticate(username=data.username, password=data.password)

    if not user:
        raise HttpError(401, "invalid_credentials")

    if not user.is_active:
        raise HttpError(403, "account_disabled")

    return set_auth_cookies(user, response)


@authentication_router.post("/logout", auth=CookieRefreshAuth())
def logout(request, response: HttpResponse):
    data = request.auth

    try:
        with transaction.atomic():
            token = RefreshToken.objects.select_related("user").select_for_update().get(token=data.get("jti"))

            token.revoked = True
            token.save()

    except ObjectDoesNotExist:
        pass

    response.delete_cookie("refresh_token")

    return {"status": "ok"}


@authentication_router.post("/refresh", response=UserOut, auth=CookieRefreshAuth())
def refresh(request, response: HttpResponse):
    data = request.auth

    try:
        error_to_raise = None
        with transaction.atomic():
            token = RefreshToken.objects.select_related("user").select_for_update().get(token=data.get("jti"))

            if not token.is_active:
                if token.used:
                    RefreshToken.objects.filter(user=data.get("sub")).update(revoked=True, updated_at=timezone.now())

                    error_to_raise = "token_has_already_been_used"
                else:
                    error_to_raise = "session_has_been_expired"

            if not error_to_raise and not token.user.is_active:
                error_to_raise = "user_is_inactive"

            if not error_to_raise:
                token.used = True
                token.save()
                return_data = set_auth_cookies(token.user, response)

        if error_to_raise:
            raise HttpError(401, error_to_raise)
        else:
            return return_data

    except ObjectDoesNotExist:
        raise HttpError(401, "token_does_not_exist")


@authentication_router.post("/register", response=UserOut)
def register(request, response: HttpResponse, data: UserIn):
    with transaction.atomic():
        try:
            user = User(username=data.username)
            user.set_password(data.password)
            user.save()
        except IntegrityError:
            raise HttpError(409, "user_is_already_exist")

        return set_auth_cookies(user, response)


@authentication_router.post("/csrf")
@ensure_csrf_cookie
@csrf_exempt
def get_csrf_token(request):
    return HttpResponse()
