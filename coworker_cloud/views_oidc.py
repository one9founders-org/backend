"""Auth0-shaped OIDC surface so stock OpenWorker can sign in via config.toml only.

OpenWorker calls:
  GET  https://{cloud_auth_domain}/authorize?...
  POST https://{cloud_auth_domain}/oauth/token
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuthLoginSession, AuthorizationCode
from .pkce import verify_s256
from .providers import LOGIN_SCOPES

User = get_user_model()

LOGIN_TTL = timedelta(minutes=10)
CODE_TTL = timedelta(minutes=5)


def _client_id_ok(client_id: str) -> bool:
    expected = getattr(settings, "COWORKER_CLOUD_CLIENT_ID", "") or ""
    return bool(expected) and client_id == expected


def _public_base(request) -> str:
    """Prefer configured public URL so Auth redirects match registered URIs."""
    base = getattr(settings, "COWORKER_CLOUD_PUBLIC_URL", "") or ""
    if base:
        return base.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


@require_GET
def authorize(request):
    """Start PKCE login — render One9Founders Cloud sign-in page."""
    client_id = request.GET.get("client_id", "")
    redirect_uri = request.GET.get("redirect_uri", "")
    state = request.GET.get("state", "")
    code_challenge = request.GET.get("code_challenge", "")
    method = request.GET.get("code_challenge_method", "S256")
    audience = request.GET.get("audience", "")
    scope = request.GET.get("scope", "openid profile email offline_access")

    if not _client_id_ok(client_id):
        return HttpResponseBadRequest("unknown client_id")
    if not redirect_uri or not state or not code_challenge:
        return HttpResponseBadRequest("missing OAuth parameters")
    if method != "S256":
        return HttpResponseBadRequest("only S256 PKCE is supported")

    # Allowed broker callback only (OpenWorker design).
    expected = (
        getattr(settings, "COWORKER_CLOUD_PUBLIC_URL", "") or _public_base(request)
    ).rstrip("/") + "/v1/auth/callback"
    if redirect_uri.rstrip("/") != expected.rstrip("/"):
        return HttpResponseBadRequest("redirect_uri not allowed")

    expected_aud = (getattr(settings, "COWORKER_CLOUD_AUDIENCE", "") or "").rstrip("/")
    if expected_aud and audience and audience.rstrip("/") != expected_aud:
        return HttpResponseBadRequest("audience not allowed")

    session = AuthLoginSession.objects.create(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=method,
        audience=audience,
        scope=scope,
        expires_at=timezone.now() + LOGIN_TTL,
    )

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return render(
        request,
        "coworker_cloud/signin.html",
        {
            "session_id": str(session.id),
            "google_client_id": google_client_id,
            "brand": "One9Founders Cloud",
            "error": request.GET.get("error", ""),
        },
    )


@require_GET
def authorize_google_redirect(request):
    """Server-side Google OAuth for account sign-in (no GIS popup dependency)."""
    session_id = request.GET.get("session", "")
    try:
        session = AuthLoginSession.objects.get(id=session_id)
    except (AuthLoginSession.DoesNotExist, ValueError):
        return HttpResponseBadRequest("unknown or expired sign-in session")
    if session.expires_at < timezone.now():
        session.delete()
        return HttpResponseBadRequest("sign-in session expired")

    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return HttpResponseBadRequest("GOOGLE_CLIENT_ID not configured")

    redirect_uri = _public_base(request) + "/oidc/google/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(LOGIN_SCOPES),
        "state": str(session.id),
        "access_type": "online",
        "prompt": "select_account",
    }
    return HttpResponseRedirect(
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode(params)
    )


@require_GET
def google_oidc_callback(request):
    """Google → One9: mint authorization code, bounce to broker redirect_uri."""
    error = request.GET.get("error")
    if error:
        return HttpResponseBadRequest(f"Google sign-in failed: {error}")

    code = request.GET.get("code", "")
    session_id = request.GET.get("state", "")
    try:
        session = AuthLoginSession.objects.get(id=session_id)
    except (AuthLoginSession.DoesNotExist, ValueError):
        return HttpResponseBadRequest("unknown or expired sign-in session")
    if session.expires_at < timezone.now():
        session.delete()
        return HttpResponseBadRequest("sign-in session expired")

    token_url = "https://oauth2.googleapis.com/token"
    redirect_uri = _public_base(request) + "/oidc/google/callback"
    import requests as http_requests

    resp = http_requests.post(
        token_url,
        data={
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        return HttpResponseBadRequest("Google token exchange failed")
    payload = resp.json()
    id_tok = payload.get("id_token")
    if not id_tok:
        return HttpResponseBadRequest("Google did not return an id_token")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            id_tok, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
        )
    except Exception as exc:  # noqa: BLE001 — surface to browser for setup debugging
        return HttpResponseBadRequest(f"invalid Google id_token: {exc}")

    email = (idinfo.get("email") or "").strip().lower()
    if not email:
        return HttpResponseBadRequest("Google account has no email")

    given = idinfo.get("given_name") or ""
    family = idinfo.get("family_name") or ""
    user, _created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "first_name": given,
            "last_name": family,
            "is_active": True,
        },
    )
    if given or family:
        user.first_name = given or user.first_name
        user.last_name = family or user.last_name
        user.save(update_fields=["first_name", "last_name"])

    auth_code = AuthorizationCode.objects.create(
        user=user,
        client_id=session.client_id,
        redirect_uri=session.redirect_uri,
        code_challenge=session.code_challenge,
        code_challenge_method=session.code_challenge_method,
        scope=session.scope,
        expires_at=timezone.now() + CODE_TTL,
    )
    state = session.state
    redirect_uri = session.redirect_uri
    session.delete()

    q = urllib.parse.urlencode({"code": auth_code.code, "state": state})
    sep = "&" if "?" in redirect_uri else "?"
    return HttpResponseRedirect(f"{redirect_uri}{sep}{q}")


@csrf_exempt
@require_http_methods(["POST"])
def oauth_token(request):
    """Auth0-compatible token endpoint (authorization_code + refresh_token)."""
    data = request.POST or request.POST.copy()
    if not data and request.body:
        # JSON body fallback
        import json

        try:
            data = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            data = {}

    def form_get(key, default=""):
        if hasattr(data, "get"):
            return data.get(key, default) or default
        return default

    grant = form_get("grant_type")
    if grant == "authorization_code":
        return _exchange_code(data)
    if grant == "refresh_token":
        return _refresh(data)
    return JsonResponse({"error": "unsupported_grant_type"}, status=400)


def _exchange_code(data) -> JsonResponse:
    def g(key):
        return (data.get(key) if hasattr(data, "get") else "") or ""

    code = g("code")
    redirect_uri = g("redirect_uri")
    code_verifier = g("code_verifier")
    client_id = g("client_id")

    if not _client_id_ok(client_id):
        return JsonResponse({"error": "invalid_client"}, status=401)
    try:
        row = AuthorizationCode.objects.select_related("user").get(code=code)
    except AuthorizationCode.DoesNotExist:
        return JsonResponse({"error": "invalid_grant"}, status=400)
    if not row.is_valid():
        return JsonResponse({"error": "invalid_grant"}, status=400)
    if row.redirect_uri != redirect_uri:
        return JsonResponse({"error": "invalid_grant"}, status=400)
    if row.code_challenge_method == "S256":
        if not verify_s256(code_verifier, row.code_challenge):
            return JsonResponse({"error": "invalid_grant"}, status=400)
    elif code_verifier != row.code_challenge:
        return JsonResponse({"error": "invalid_grant"}, status=400)

    row.consumed_at = timezone.now()
    row.save(update_fields=["consumed_at"])

    refresh = RefreshToken.for_user(row.user)
    access = refresh.access_token
    # Align lifetime with SimpleJWT ACCESS_TOKEN_LIFETIME when present.
    lifetime = getattr(settings, "SIMPLE_JWT", {}).get("ACCESS_TOKEN_LIFETIME")
    expires_in = int(lifetime.total_seconds()) if lifetime else 3600
    return JsonResponse(
        {
            "access_token": str(access),
            "refresh_token": str(refresh),
            "token_type": "Bearer",
            "expires_in": expires_in,
        }
    )


def _refresh(data) -> JsonResponse:
    def g(key):
        return (data.get(key) if hasattr(data, "get") else "") or ""

    client_id = g("client_id")
    if not _client_id_ok(client_id):
        return JsonResponse({"error": "invalid_client"}, status=401)
    raw = g("refresh_token")
    try:
        refresh = RefreshToken(raw)
        access = refresh.access_token
    except Exception:
        return JsonResponse({"error": "invalid_grant"}, status=400)
    lifetime = getattr(settings, "SIMPLE_JWT", {}).get("ACCESS_TOKEN_LIFETIME")
    expires_in = int(lifetime.total_seconds()) if lifetime else 3600
    body = {
        "access_token": str(access),
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    # Rotate refresh when SimpleJWT is configured to; otherwise echo.
    try:
        body["refresh_token"] = str(refresh)
    except Exception:
        body["refresh_token"] = raw
    return JsonResponse(body)
