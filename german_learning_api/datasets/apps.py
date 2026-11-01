from django.apps import AppConfig


class DatasetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "datasets"

    def ready(self):
        from datasets import signals  # noqa: F401
