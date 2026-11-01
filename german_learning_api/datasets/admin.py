from django.contrib import admin

from datasets.models import UserDataset


@admin.register(UserDataset)
class UserDatasetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "created_at", "updated_at")
    search_fields = ("name", "user__username")
    readonly_fields = ("tags", "extra_words")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, "user") if obj is not None else fields
