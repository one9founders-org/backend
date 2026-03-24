import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def analyse_tool(request):
    try:
        body = json.loads(request.body)
        tool_name = body.get('tool_name', '').strip()
        if not tool_name:
            return JsonResponse({"error": "tool_name is required"}, status=400)
        from .tasks import run_sentiment_for_tool
        result = run_sentiment_for_tool(tool_name)
        return JsonResponse(result, status=200)
    except Exception as e:
        logger.error(f"[View] Error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def get_sentiment(request, tool_name):
    try:
        from .models import ToolSentiment
        sentiment = ToolSentiment.objects.get(tool_name=tool_name)
        return JsonResponse({
            "tool": sentiment.tool_name,
            "score": sentiment.overall_score,
            "label": sentiment.sentiment_label,
            "confidence": sentiment.confidence,
            "source_count": sentiment.source_count,
            "top_praises": sentiment.top_praises,
            "top_complaints": sentiment.top_complaints,
            "red_flags": sentiment.red_flags,
            "summary": sentiment.one_line_summary,
            "last_analysed": str(sentiment.last_analysed),
        })
    except ToolSentiment.DoesNotExist:
        return JsonResponse({"error": "No sentiment data found"}, status=404)


@require_http_methods(["GET"])
def get_sentiment_summary(request, tool_name):
    try:
        from .models import ToolSentiment
        sentiment = ToolSentiment.objects.get(tool_name=tool_name)
        return JsonResponse({
            "tool": sentiment.tool_name,
            "score": sentiment.overall_score,
            "label": sentiment.sentiment_label,
            "confidence": sentiment.confidence,
            "summary": sentiment.one_line_summary,
        })
    except ToolSentiment.DoesNotExist:
        return JsonResponse({"error": "No sentiment data found"}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def run_bulk_pipeline(request):
    try:
        body = json.loads(request.body)
        limit = body.get('limit', 50)
        from .tasks import run_bulk_sentiment_pipeline
        results = run_bulk_sentiment_pipeline(limit=limit)
        return JsonResponse({
            "status": "completed",
            "total": len(results),
            "results": results
        })
    except Exception as e:
        logger.error(f"[View] Bulk pipeline error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def get_pipeline_stats(request):
    from .models import ToolSentiment
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=48)
    total = ToolSentiment.objects.count()
    fresh = ToolSentiment.objects.filter(last_analysed__gte=cutoff).count()
    stale = ToolSentiment.objects.filter(last_analysed__lt=cutoff).count()
    red_flags = ToolSentiment.objects.exclude(red_flags=[]).count()
    positive = ToolSentiment.objects.filter(sentiment_label='positive').count()
    negative = ToolSentiment.objects.filter(sentiment_label='negative').count()
    mixed = ToolSentiment.objects.filter(sentiment_label='mixed').count()
    insufficient = ToolSentiment.objects.filter(sentiment_label='insufficient_data').count()
    return JsonResponse({
        "total_analysed": total,
        "fresh_last_48h": fresh,
        "stale": stale,
        "tools_with_red_flags": red_flags,
        "breakdown": {
            "positive": positive,
            "mixed": mixed,
            "negative": negative,
            "insufficient_data": insufficient
        }
    })


@require_http_methods(["GET"])
def get_red_flag_tools(request):
    from .models import ToolSentiment
    tools = ToolSentiment.objects.exclude(red_flags=[])
    data = []
    for t in tools:
        data.append({
            "tool": t.tool_name,
            "red_flags": t.red_flags,
            "score": t.overall_score,
            "last_analysed": str(t.last_analysed)
        })
    return JsonResponse({"total": len(data), "tools": data})


@require_http_methods(["GET"])
def get_top_rated_tools(request):
    from .models import ToolSentiment
    limit = int(request.GET.get('limit', 10))
    tools = ToolSentiment.objects.filter(
        sentiment_label='positive',
        confidence__in=['medium', 'high']
    ).order_by('-overall_score')[:limit]
    data = []
    for t in tools:
        data.append({
            "tool": t.tool_name,
            "score": t.overall_score,
            "confidence": t.confidence,
            "summary": t.one_line_summary,
            "top_praises": t.top_praises
        })
    return JsonResponse({"total": len(data), "tools": data})


@require_http_methods(["GET"])
def get_pending_tools(request):
    from .models import ToolSentiment
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=48)
    stale = list(ToolSentiment.objects.filter(
        last_analysed__lt=cutoff
    ).values_list('tool_name', flat=True)[:50])
    return JsonResponse({"pending_count": len(stale), "tools": stale})