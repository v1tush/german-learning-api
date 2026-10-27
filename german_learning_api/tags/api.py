from authentication.auth import BotAuth, GlobalAuth
from ninja import Router


tags_router = Router(auth=[GlobalAuth(), BotAuth()])

