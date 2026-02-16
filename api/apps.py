import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        import os

        if os.environ.get("RUN_MAIN") == "true" or not os.environ.get(
            "DJANGO_DEV_SERVER"
        ):
            try:
                from api.faiss_search import FAISSSearchService

                service = FAISSSearchService.get_instance()
                if service.load_index():
                    logger.info("FAISS index loaded: %d tools", service.tool_count)
                else:
                    logger.info(
                        "FAISS index not found. "
                        "Run 'python manage.py build_faiss_index' to create it."
                    )
            except Exception as e:
                logger.warning("Failed to load FAISS index on startup: %s", e)
