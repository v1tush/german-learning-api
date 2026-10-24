from ninja import Router

users_router = Router()
me_router = Router()

users_router.add_router("/me/", me_router)


@me_router.get("/")  # TODO: append "response = schema"
def me(request):
    return request.auth
