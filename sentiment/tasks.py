import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def run_sentiment_for_tool(tool_name: str):
    """
    Run sentiment analysis for a single tool.
    Called by the bulk pipeline or manually.
    """
    try:
        from .agent import run_sentiment_agent
        result = run_sentiment_agent(tool_name)
        logger.info(f"[Task] Completed sentiment for: {tool_name}")
        return {
            "tool": tool_name,
            "status": "success",
            "sentiment": result.sentiment_label,
            "score": result.overall_score,
            "confidence": result.confidence
        }
    except Exception as e:
        logger.error(f"[Task] Failed for {tool_name}: {e}")
        return {
            "tool": tool_name,
            "status": "failed",
            "error": str(e)
        }


def run_bulk_sentiment_pipeline(limit: int = 50):
    """
    Processes a batch of tools that need sentiment analysis.
    This is what n8n will trigger every 48 hours.
    """
    from .models import ToolSentiment

    cutoff = timezone.now() - timedelta(hours=48)

    # Get tool names that are stale or never analysed
    stale = ToolSentiment.objects.filter(
        last_analysed__lt=cutoff
    ).values_list('tool_name', flat=True)[:limit]

    # For now we also support passing tool names directly
    tool_names = list(stale)

    logger.info(f"[Pipeline] Processing {len(tool_names)} tools")

    results = []
    for tool_name in tool_names:
        result = run_sentiment_for_tool(tool_name)
        results.append(result)

    success = len([r for r in results if r['status'] == 'success'])
    failed = len([r for r in results if r['status'] == 'failed'])

    logger.info(f"[Pipeline] Done. {success} succeeded, {failed} failed")
    return results