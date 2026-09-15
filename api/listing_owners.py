"""Who may edit a public directory listing."""

from django.db.models import Q

from .models import Tool, ToolSubmission


def normalized_email(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    return (getattr(user, "email", None) or "").strip().lower()


def owned_tools_queryset(user):
    email = normalized_email(user)
    if not email:
        return Tool.objects.none()
    owned = ToolSubmission.objects.filter(
        status="approved", submitter_email__iexact=email
    )
    return Tool.objects.filter(
        Q(pk__in=owned.exclude(approved_tool_id=None).values("approved_tool_id"))
        | Q(
            name__in=owned.filter(approved_tool__isnull=True).values("name"),
        )
    ).distinct()


def user_owns_listing(user, tool) -> bool:
    if tool is None:
        return False
    return owned_tools_queryset(user).filter(pk=tool.pk).exists()


def owned_listings_payload(user) -> list[dict]:
    return list(
        owned_tools_queryset(user)
        .filter(is_active=True)
        .order_by("name")
        .values("slug", "name")
    )
