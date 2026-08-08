from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()


def user_from_bearer(request) -> Optional[User]:
    """Resolve the OpenWorker cloud session JWT from Authorization: Bearer."""
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    if not header.lower().startswith("bearer "):
        return None
    raw = header.split(" ", 1)[1].strip()
    if not raw:
        return None
    try:
        auth = JWTAuthentication()
        validated = auth.get_validated_token(raw)
        return auth.get_user(validated)
    except (InvalidToken, TokenError, User.DoesNotExist):
        return None
