from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
<<<<<<< HEAD
        from . import scheduler
        scheduler.start()
=======
        import api.signals  # noqa: F401
>>>>>>> origin/main
