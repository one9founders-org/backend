from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Start the background news scheduler when the app is ready
        try:
            from . import scheduler

            scheduler.start()
        except ImportError:
            # Handle cases where scheduler might not be present (e.g. initial setup)
            pass
        except Exception:
            # Prevent app from crashing if scheduler fails
            pass
