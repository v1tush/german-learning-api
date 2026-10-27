from authentication.auth import BotAuth, GlobalAuth
from ninja import Router

from users.schemas import UserMeOut

users_router = Router(auth=[GlobalAuth(), BotAuth()])
me_router = Router()

users_router.add_router("/me/", me_router)


@me_router.get("/", response=UserMeOut)
def me(request):
    return request.auth
