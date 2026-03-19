import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Tool, ToolSuggestion

logger = logging.getLogger(__name__)


class ExtensionRateThrottle(AnonRateThrottle):
    scope = "extension"
    rate = "60/min"


def verify_extension_api_key(request):
    """Verify the X-Extension-Key header against the configured API key."""
    api_key = getattr(settings, "EXTENSION_API_KEY", "")
    if not api_key:
        return True
    provided_key = request.headers.get("X-Extension-Key", "")
    return provided_key == api_key


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([ExtensionRateThrottle])
def extension_lookup(request):
    """Look up a tool by domain for the Chrome extension."""
    # Verify API key
    if not verify_extension_api_key(request):
        return Response(
            {"error": "Invalid or missing API key"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    domain = request.query_params.get("domain", "").strip().lower()
    if not domain:
        return Response(
            {"error": "domain query parameter is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Strip www. prefix from the queried domain
    if domain.startswith("www."):
        domain = domain[4:]

    # Check cache first
    cache_key = f"extension_lookup:{domain}"
    cached = cache.get(cache_key)
    if cached is not None:
        if not cached.get("found", True):
            return Response(cached, status=status.HTTP_404_NOT_FOUND)
        return Response(cached)

    # 1. Exact match on domain field
    tool = (
        Tool.objects.filter(domain=domain, is_active=True)
        .prefetch_related("categories", "alternatives")
        .first()
    )

    # 2. Endswith match (e.g. notion.so matches tool with domain notion.so)
    if not tool:
        tool = (
            Tool.objects.filter(domain__endswith=domain, is_active=True)
            .prefetch_related("categories", "alternatives")
            .first()
        )

    # 3. No match
    if not tool:
        not_found = {"found": False}
        cache.set(cache_key, not_found, 3600)
        return Response(not_found, status=status.HTTP_404_NOT_FOUND)

    # Build category string from first category
    categories = tool.categories.all()
    category_name = categories[0].name if categories else ""

    # Determine security validation status
    security_validated = tool.security_score is not None and tool.security_score >= 50

    # Get pricing display string
    pricing = tool.pricing_type or ""
    if pricing:
        pricing = pricing.capitalize()

    # Build alternatives list
    alternatives = []
    for alt in tool.alternatives.filter(is_active=True)[:5]:
        alternatives.append({"name": alt.name, "slug": alt.slug})

    result = {
        "found": True,
        "tool": {
            "name": tool.name,
            "slug": tool.slug,
            "category": category_name,
            "description": tool.short_description or tool.description[:200],
            "security_validated": security_validated,
            "security_score": tool.security_score,
            "pricing": pricing,
            "website_url": tool.website or "",
            "one9founders_url": f"https://one9founders.com/tool/{tool.slug}",
            "alternatives": alternatives,
        },
    }

    # Cache for 1 hour
    cache.set(cache_key, result, 3600)
    return Response(result)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ExtensionRateThrottle])
def extension_suggest(request):
    """Accept tool suggestions from the Chrome extension."""
    # Verify API key
    if not verify_extension_api_key(request):
        return Response(
            {"error": "Invalid or missing API key"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    domain = request.data.get("domain", "").strip().lower()
    if not domain:
        return Response(
            {"error": "domain is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    suggested_by = request.data.get("suggested_by", "extension_user")

    # Avoid duplicate suggestions for the same domain
    if ToolSuggestion.objects.filter(domain=domain, status="pending").exists():
        return Response(
            {"message": "This domain has already been suggested. Thanks!"},
            status=status.HTTP_200_OK,
        )

    ToolSuggestion.objects.create(
        domain=domain,
        suggested_by=suggested_by,
    )

    return Response(
        {"message": "Thanks! We'll review this tool."},
        status=status.HTTP_201_CREATED,
    )
