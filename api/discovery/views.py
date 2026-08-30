import hmac

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.discovery.pipeline import (
    run_india_and_new_discovery,
    run_new_tool_discovery,
    run_refresh_descriptions,
)


def _secret_matches(request) -> bool:
    expected = getattr(settings, "DISCOVERY_TRIGGER_SECRET", "") or ""
    provided = request.headers.get("X-Trigger-Secret", "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([AllowAny])
def run_discovery_trigger(request):
    """cron-job.org trigger. Not for public clients or sitemaps."""
    if not _secret_matches(request):
        return Response({"detail": "Forbidden"}, status=403)

    job = (request.query_params.get("job") or "both").lower()
    if job not in {"both", "discovery", "refresh", "india"}:
        return Response(
            {"detail": "job must be both, discovery, refresh, or india"},
            status=400,
        )

    payload = {}
    if job == "india":
        payload["india"] = run_india_and_new_discovery()
        return Response(payload)
    if job in {"both", "discovery"}:
        payload["discovery"] = run_new_tool_discovery()
    if job in {"both", "refresh"}:
        payload["refresh"] = run_refresh_descriptions(limit=50)
    return Response(payload)
