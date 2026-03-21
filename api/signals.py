import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="api.ToolSuggestion")
def auto_process_suggestion(sender, instance, created, **kwargs):
    """Auto-process new ToolSuggestion entries with OpenAI."""
    if created and instance.status == "pending":
        thread = threading.Thread(
            target=_process_suggestion_safe,
            args=(instance.pk,),
        )
        thread.daemon = True
        thread.start()


def _process_suggestion_safe(suggestion_pk):
    """Process a suggestion in a background thread, catching all errors."""
    try:
        from api.models import ToolSuggestion
        from api.services.tool_enrichment import process_tool_suggestion

        suggestion = ToolSuggestion.objects.get(pk=suggestion_pk)
        process_tool_suggestion(suggestion)
    except Exception as e:
        logger.error("Error processing suggestion %s: %s", suggestion_pk, e)
