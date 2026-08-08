"""OpenWorker Cloud broker API — paths OpenWorker calls on cloud_base_url."""

from __future__ import annotations

import os
import urllib.parse
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .authz import user_from_bearer
from .models import CloudConnection, ManagedOAuthPending
from .providers import GOOGLE_SCOPES, PROVIDER_FOR_CONNECTOR

PENDING_TTL = timedelta(minutes=10)


def _public_base(request) -> str:
    base = getattr(settings, "COWORKER_CLOUD_PUBLIC_URL", "") or ""
    if base:
        return base.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def _json_error(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _loopback_port_from_state(state: str) -> int:
    """Parse `{random}.{port}` from OpenWorker PKCE state; default 8765."""
    port = 8765
    if "." in state:
        maybe = state.rsplit(".", 1)[-1]
        if maybe.isdigit():
            n = int(maybe)
            if 1 <= n <= 65535:
                port = n
    return port


def _is_loopback_oauth_callback(url: str) -> bool:
    """Managed OAuth may only POST tokens to the local OpenWorker sidecar."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or parts.hostname != "127.0.0.1":
        return False
    if parts.port is None or not (1 <= parts.port <= 65535):
        return False
    return parts.path.rstrip("/") == "/oauth/callback"


@require_GET
def auth_callback_bounce(request):
    """Stable broker callback Auth0/One9 OIDC redirects to; bounce to sidecar port in state."""
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    error = request.GET.get("error", "")
    port = _loopback_port_from_state(state)
    q = {}
    if error:
        q["error"] = error
    if code:
        q["code"] = code
    if state:
        q["state"] = state
    target = f"http://127.0.0.1:{port}/auth/callback?" + urllib.parse.urlencode(q)
    return HttpResponseRedirect(target)


@require_GET
def me(request):
    user = user_from_bearer(request)
    if not user:
        return _json_error("unauthorized", 401)
    return JsonResponse(
        {
            "user": {
                "email": user.email,
                "user_id": f"one9_{user.id}",
                "name": user.get_full_name() or user.first_name or user.email,
            }
        }
    )


@require_GET
def connections(request):
    user = user_from_bearer(request)
    if not user:
        return _json_error("unauthorized", 401)
    rows = CloudConnection.objects.filter(user=user).order_by("-updated_at")
    return JsonResponse(
        {
            "connections": [
                {
                    "connection_id": str(c.id),
                    "connector": c.connector,
                    "provider": c.provider,
                    "status": c.status,
                    "account": c.account,
                    "account_id": c.account_id,
                    "tenant_metadata": c.tenant_metadata or {},
                }
                for c in rows
            ]
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def connection_disconnect(request, connection_id: str):
    user = user_from_bearer(request)
    if not user:
        return _json_error("unauthorized", 401)
    try:
        row = CloudConnection.objects.get(id=connection_id, user=user)
    except (CloudConnection.DoesNotExist, ValueError):
        return JsonResponse({"ok": True})  # idempotent
    row.status = "disconnected"
    row.access_token = ""
    row.refresh_token = ""
    row.save(update_fields=["status", "access_token", "refresh_token", "updated_at"])
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def telemetry_events(request):
    user = user_from_bearer(request)
    if not user:
        return _json_error("unauthorized", 401)
    # Accept and discard content-free session events (OpenWorker Phase 5 shape).
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def oauth_start(request, provider: str):
    user = user_from_bearer(request)
    if not user:
        return _json_error("not signed in", 401)

    import json

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        body = {}

    connector = (body.get("connector") or "").strip()
    sidecar_redirect = (body.get("redirect") or "").strip()
    app_state = (body.get("app_state") or "").strip()
    access = (body.get("access") or "").strip()
    flow = (body.get("flow") or "").strip()

    if PROVIDER_FOR_CONNECTOR.get(connector) != provider:
        return _json_error(f"{connector} is not a {provider} connector")
    if not _is_loopback_oauth_callback(sidecar_redirect):
        return _json_error("redirect must be http://127.0.0.1:{port}/oauth/callback")
    if not app_state:
        return _json_error("app_state required")

    if provider != "google":
        return _json_error(
            f"provider '{provider}' not implemented yet on One9Founders Cloud "
            "(google/gmail/calendar/drive are available)",
            501,
        )

    scopes = GOOGLE_SCOPES.get(connector)
    if not scopes:
        return _json_error(f"no Google scopes configured for {connector}")

    pending = ManagedOAuthPending.objects.create(
        user=user,
        provider=provider,
        connector=connector,
        app_state=app_state,
        sidecar_redirect=sidecar_redirect,
        access=access,
        flow=flow,
        expires_at=timezone.now() + PENDING_TTL,
    )

    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return _json_error("GOOGLE_CLIENT_ID not configured", 500)

    callback = _public_base(request) + "/v1/oauth/google/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": callback,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": str(pending.id),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return JsonResponse(
        {
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?"
            + urllib.parse.urlencode(params),
            "app_state": app_state,
        }
    )


@require_GET
def oauth_google_callback(request):
    """Google connector consent → HTML page that form-POSTs tokens to the sidecar."""
    error = request.GET.get("error")
    pending_id = request.GET.get("state", "")
    code = request.GET.get("code", "")

    try:
        pending = ManagedOAuthPending.objects.select_related("user").get(id=pending_id)
    except (ManagedOAuthPending.DoesNotExist, ValueError):
        return HttpResponseBadRequest("unknown or expired connection attempt")
    if pending.expires_at < timezone.now():
        pending.delete()
        return HttpResponseBadRequest("connection attempt expired")

    if error:
        return render(
            request,
            "coworker_cloud/post_tokens.html",
            {
                "sidecar_redirect": pending.sidecar_redirect,
                "fields": {
                    "error": error,
                    "connector": pending.connector,
                    "provider": pending.provider,
                    "app_state": pending.app_state,
                },
            },
        )

    import requests as http_requests

    callback = _public_base(request) + "/v1/oauth/google/callback"
    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "redirect_uri": callback,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        pending.delete()
        return HttpResponseBadRequest("Google token exchange failed")
    tok = resp.json()
    access_token = tok.get("access_token", "")
    refresh_token = tok.get("refresh_token", "")
    expires_in = str(tok.get("expires_in") or 3600)
    scope = tok.get("scope", "")

    # Resolve account email for multi-account keying.
    account = ""
    account_id = ""
    try:
        ui = http_requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if ui.status_code == 200:
            info = ui.json()
            account = info.get("email") or ""
            account_id = info.get("id") or ""
    except Exception:
        pass

    # Upsert by (user, connector, account). Keep prior refresh if Google omits it.
    defaults = {
        "provider": pending.provider,
        "status": "connected",
        "account": account,
        "scope": scope,
        "access_token": access_token,
        "expires_at": timezone.now() + timedelta(seconds=int(expires_in)),
        "tenant_metadata": {},
    }
    if refresh_token:
        defaults["refresh_token"] = refresh_token
    conn, _created = CloudConnection.objects.update_or_create(
        user=pending.user,
        connector=pending.connector,
        account_id=account_id or "",
        defaults=defaults,
    )

    fields = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "scope": scope,
        "connection_id": str(conn.id),
        "provider": pending.provider,
        "connector": pending.connector,
        "account": account,
        "account_id": account_id,
        "app_state": pending.app_state,
    }
    sidecar = pending.sidecar_redirect
    pending.delete()
    return render(
        request,
        "coworker_cloud/post_tokens.html",
        {"sidecar_redirect": sidecar, "fields": fields},
    )


@csrf_exempt
@require_http_methods(["POST"])
def oauth_refresh(request, provider: str):
    user = user_from_bearer(request)
    if not user:
        return _json_error("unauthorized", 401)
    import json

    try:
        body = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        body = {}

    connection_id = body.get("connection_id") or ""
    refresh_token = body.get("refresh_token") or ""
    try:
        conn = CloudConnection.objects.get(id=connection_id, user=user, provider=provider)
    except (CloudConnection.DoesNotExist, ValueError):
        return _json_error("unknown connection", 404)
    rt = refresh_token or conn.refresh_token
    if not rt:
        return _json_error("no refresh_token", 400)

    if provider != "google":
        return _json_error("unsupported provider", 501)

    import requests as http_requests

    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "refresh_token": rt,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        return _json_error("refresh failed", 400)
    fresh = resp.json()
    conn.access_token = fresh.get("access_token", "")
    if fresh.get("refresh_token"):
        conn.refresh_token = fresh["refresh_token"]
    expires_in = int(fresh.get("expires_in") or 3600)
    conn.expires_at = timezone.now() + timedelta(seconds=expires_in)
    conn.save(
        update_fields=["access_token", "refresh_token", "expires_at", "updated_at"]
    )
    out = {
        "access_token": conn.access_token,
        "expires_in": expires_in,
    }
    if fresh.get("refresh_token"):
        out["refresh_token"] = fresh["refresh_token"]
    return JsonResponse(out)


@require_GET
def cloud_home(request):
    """Simple landing so humans hitting the cloud base URL see One9 branding."""
    public = _public_base(request)
    auth_domain = urllib.parse.urlsplit(public).netloc or public
    return render(
        request,
        "coworker_cloud/home.html",
        {
            "public_url": public,
            "auth_domain": auth_domain,
            "client_id": getattr(settings, "COWORKER_CLOUD_CLIENT_ID", ""),
        },
    )
