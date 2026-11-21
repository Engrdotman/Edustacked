from django.apps import AppConfig


class SchoolFeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.school_fees"
    verbose_name = "School fees"

    def ready(self):
        from . import signals  # noqa: F401
