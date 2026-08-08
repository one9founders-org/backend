from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def _code() -> str:
    return secrets.token_urlsafe(32)


class AuthLoginSession(models.Model):
    """PKCE login pending between /authorize and Google callback → code mint."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=128)
    redirect_uri = models.TextField()
    state = models.CharField(max_length=256)
    code_challenge = models.CharField(max_length=128)
    code_challenge_method = models.CharField(max_length=16, default="S256")
    audience = models.CharField(max_length=256, blank=True, default="")
    scope = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["expires_at"])]


class AuthorizationCode(models.Model):
    """One-time code OpenWorker exchanges at /oauth/token."""

    code = models.CharField(max_length=128, unique=True, default=_code)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    client_id = models.CharField(max_length=128)
    redirect_uri = models.TextField()
    code_challenge = models.CharField(max_length=128)
    code_challenge_method = models.CharField(max_length=16, default="S256")
    scope = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self) -> bool:
        return self.consumed_at is None and self.expires_at > timezone.now()


class CloudConnection(models.Model):
    """Metadata for a managed connector; tokens are delivered to the desktop, not kept here long-term.

    We store refresh material server-side only so /v1/oauth/{provider}/refresh works —
    same broker role OpenWorker Cloud plays. Access tokens are minted/returned to the
    local OpenWorker sidecar and are not the source of truth for chat/files.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cloud_connections"
    )
    provider = models.CharField(max_length=64)  # google, slack, github, …
    connector = models.CharField(max_length=64)  # gmail, google_calendar, …
    status = models.CharField(max_length=32, default="connected")
    account = models.CharField(max_length=255, blank=True, default="")
    account_id = models.CharField(max_length=255, blank=True, default="")
    scope = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")
    access_token = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    tenant_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "connector"]),
            models.Index(fields=["user", "status"]),
        ]


class ManagedOAuthPending(models.Model):
    """In-flight one-click connector OAuth (between /start and provider callback)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    provider = models.CharField(max_length=64)
    connector = models.CharField(max_length=64)
    app_state = models.CharField(max_length=128)
    sidecar_redirect = models.TextField()  # http://127.0.0.1:{port}/oauth/callback
    access = models.CharField(max_length=64, blank=True, default="")
    flow = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
