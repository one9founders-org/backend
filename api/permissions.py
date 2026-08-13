import hmac

from django.conf import settings
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission


def _is_staff(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff)


class IsStaffOrNotFound(BasePermission):
    """Allow staff users only. Everyone else gets 404, not 401/403."""

    def has_permission(self, request, view):
        if _is_staff(request):
            return True
        raise NotFound()


class IsStaffOrReadOnly(BasePermission):
    """Public reads; staff-only writes. Non-staff writes return 404."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if _is_staff(request):
            return True
        raise NotFound()


class IsStaffOrPipelineKey(BasePermission):
    """Allow staff JWT *or* a shared pipeline ingest key. Otherwise 404."""

    def has_permission(self, request, view):
        expected = getattr(settings, "PIPELINE_API_KEY", "") or ""
        provided = request.headers.get("X-Pipeline-Key", "")
        if expected and provided and hmac.compare_digest(provided, expected):
            return True
        if _is_staff(request):
            return True
        raise NotFound()
