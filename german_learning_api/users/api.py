from authentication.auth import BotAuth, BotServiceAuth, GlobalAuth
from django.http import HttpResponse
from ninja import Router

from users.schemas import TelegramLinkConfirmIn, TelegramLinkConfirmOut, TelegramLinkIssueOut, UserMeOut
from users.services import confirm_telegram_link, issue_telegram_link, parse_telegram_id

users_router = Router(auth=[GlobalAuth(), BotAuth()])
me_router = Router()

users_router.add_router("/me/", me_router)


@me_router.get("/", response=UserMeOut)
def me(request):
    return request.auth


@me_router.post("/telegram-link", response={201: TelegramLinkIssueOut}, auth=GlobalAuth())
def create_telegram_link(request, response: HttpResponse):
    response["Cache-Control"] = "no-store"
    return 201, issue_telegram_link(request.auth)


@users_router.post("/telegram-link/confirm", response=TelegramLinkConfirmOut, auth=BotServiceAuth())
def confirm_telegram_link_from_bot(request, data: TelegramLinkConfirmIn):
    telegram_id = parse_telegram_id(request.headers.get("X-Telegram-ID"))
    return confirm_telegram_link(data.token, telegram_id)
