from authentication.api import authentication_router
from authentication.auth import GlobalAuth
from datasets.api import datasets_router
from ninja import NinjaAPI
from schedules.api import schedules_router
from tags.api import tags_router
from translations.api import translations_router
from users.api import users_router
from words.api import words_router

api = NinjaAPI(title="German learning API", version="1.0.0")


@api.get("/ping", auth=GlobalAuth())
def penis(request):
    return "ok"


api.add_router("/translations/", translations_router, tags=["Translations"])
api.add_router("/users/", users_router, tags=["Users"])
api.add_router("/authentication/", authentication_router, tags=["Authentication"])
api.add_router("/words/", words_router, tags=["Words"])
api.add_router("/tags/", tags_router, tags=["Tags"])
api.add_router("/datasets/", datasets_router, tags=["Datasets"])
api.add_router("/schedules/", schedules_router, tags=["Schedules"])
