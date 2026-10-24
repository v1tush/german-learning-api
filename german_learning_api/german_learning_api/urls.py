from django.contrib import admin
from django.urls import path

from german_learning_api.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
