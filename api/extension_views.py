import hmac
import logging
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Tool, ToolSubmission

logger = logging.getLogger(__name__)


def _verify_extension_key(request):
    """Verify the X-Extension-Key header matches the configured key."""
    key = request.headers.get("X-Extension-Key", "")
    expected = getattr(settings, "EXTENSION_API_KEY", "")
    if not expected or not key:
        return False
    return hmac.compare_digest(key, expected)


def _extract_domain(url):
    """Extract domain from a URL, stripping www. prefix."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        return hostname.removeprefix("www.")
    except Exception:
        return ""


@api_view(["GET"])
@permission_classes([AllowAny])
def extension_lookup(request):
    """Look up a tool by its website domain."""
    if not _verify_extension_key(request):
        return Response(
            {"error": "Invalid or missing API key"},
            status=status.HTTP_403_FORBIDDEN,
        )

    domain = request.query_params.get("domain", "").strip().lower()
    if not domain:
        return Response(
            {"error": "domain parameter is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Search for a tool whose website contains the domain
    # Use DB-level filter to narrow candidates, then verify exact domain match
    candidates = Tool.objects.filter(
        is_active=True, website__icontains=domain
    ).prefetch_related("categories", "alternatives")

    matched_tool = None
    for tool in candidates:
        tool_domain = _extract_domain(tool.website).lower()
        if tool_domain == domain:
            matched_tool = tool
            break

    if not matched_tool:
        return Response({"found": False})

    # Build the response matching what the extension expects
    categories = list(matched_tool.categories.values_list("name", flat=True))
    alternatives = list(
        matched_tool.alternatives.filter(is_active=True).values("name", "slug")[:5]
    )

    # Determine pricing label
    pricing_label = ""
    if matched_tool.pricing_models:
        pricing_label = ", ".join(
            p.replace("_", " ").title() for p in matched_tool.pricing_models
        )

    tool_data = {
        "name": matched_tool.name,
        "slug": matched_tool.slug,
        "description": matched_tool.short_description or matched_tool.description[:200],
        "category": categories[0] if categories else None,
        "pricing": pricing_label or None,
        "security_score": None,  # Placeholder for future security scoring
        "alternatives": alternatives,
        "one9founders_url": f"https://one9founders.com/tool/{matched_tool.slug}",
    }

    return Response({"found": True, "tool": tool_data})


@api_view(["POST"])
@permission_classes([AllowAny])
def extension_suggest(request):
    """Accept a tool suggestion from the Chrome extension."""
    if not _verify_extension_key(request):
        return Response(
            {"error": "Invalid or missing API key"},
            status=status.HTTP_403_FORBIDDEN,
        )

    domain = request.data.get("domain", "").strip()
    suggested_by = request.data.get("suggested_by", "extension_user")

    if not domain:
        return Response(
            {"error": "domain is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if this domain already exists as a tool
    domain_lower = domain.lower()
    candidates = Tool.objects.filter(is_active=True, website__icontains=domain_lower)
    for tool in candidates:
        tool_domain = _extract_domain(tool.website).lower()
        if tool_domain == domain_lower:
            return Response(
                {
                    "status": "exists",
                    "message": "This tool is already in our directory",
                },
                status=status.HTTP_200_OK,
            )

    # Check if already suggested — normalize to lowercase https URL
    website_url = f"https://{domain_lower}"
    existing_submission = ToolSubmission.objects.filter(
        website__iexact=website_url, status="pending"
    ).first()
    if existing_submission:
        return Response(
            {
                "status": "already_suggested",
                "message": "This tool has already been suggested and is pending review",
            },
            status=status.HTTP_200_OK,
        )

    # Create a new submission
    ToolSubmission.objects.create(
        name=domain_lower.split(".")[0].title(),
        description=f"Tool suggested via Chrome extension from domain: {domain_lower}",
        website=website_url,
        submitter_email="extension@one9founders.com",
        submitter_name=suggested_by,
    )

    logger.info("Extension tool suggestion created for domain: %s", domain)

    return Response(
        {"status": "submitted", "message": "Tool suggestion received. Thank you!"},
        status=status.HTTP_201_CREATED,
    )
