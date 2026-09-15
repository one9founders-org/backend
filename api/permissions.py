import hmac

from django.conf import settings
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .listing_owners import user_owns_listing


def _is_staff(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff)


def _is_authenticated(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


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


class IsStaffOrListingOwnerOrReadOnly(BasePermission):
    """Public reads; staff create/delete; staff or listing owner update."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        action = getattr(view, "action", None)
        if action in ("create", "destroy") or request.method == "DELETE":
            if _is_staff(request):
                return True
            raise NotFound()
        if request.method in ("PUT", "PATCH"):
            if _is_staff(request) or _is_authenticated(request):
                return True
            raise NotFound()
        raise NotFound()

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if _is_staff(request):
            return True
        if request.method in ("PUT", "PATCH") and user_owns_listing(request.user, obj):
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
