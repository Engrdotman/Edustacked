from django.apps import AppConfig


class SchoolsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.schools"
    label = "schools"

    def ready(self):
        from . import signals  # noqa: F401
