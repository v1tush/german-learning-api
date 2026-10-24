from ninja import NinjaAPI


from translations.api import translations_router
api = NinjaAPI(title="German learning API", version='1.0.0')


api.add_router('/translations/', translations_router)
