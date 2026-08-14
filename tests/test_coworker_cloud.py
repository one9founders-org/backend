"""One9Founders Cloud broker — PKCE login, allowlists, /v1/me, Google managed start."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from coworker_cloud.models import (
    AuthorizationCode,
    CloudConnection,
    ManagedOAuthPending,
)
from coworker_cloud.pkce import b64url, verify_s256
from coworker_cloud.views_broker import (
    _is_loopback_oauth_callback,
    _loopback_port_from_state,
)

User = get_user_model()

CLIENT_ID = "one9founders-openworker-dev"
PUBLIC = "http://127.0.0.1:8000"
AUDIENCE = "http://127.0.0.1:8000"
REDIRECT = f"{PUBLIC}/v1/auth/callback"


def _verifier_challenge():
    verifier = b64url(b"test-verifier-bytes-for-pkce-s256!!")
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


@pytest.fixture
def api():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="founder@example.com",
        email="founder@example.com",
        password="x",
        first_name="Founder",
    )


@pytest.fixture
def bearer(user):
    return str(RefreshToken.for_user(user).access_token)


@pytest.fixture(autouse=True)
def coworker_cloud_settings(settings):
    settings.COWORKER_CLOUD_CLIENT_ID = CLIENT_ID
    settings.COWORKER_CLOUD_PUBLIC_URL = PUBLIC
    settings.COWORKER_CLOUD_AUDIENCE = AUDIENCE


@pytest.mark.django_db
class TestAuthorizeAllowlist:
    def test_rejects_unknown_client(self, api):
        _, c = _verifier_challenge()
        r = api.get(
            "/authorize",
            {
                "client_id": "wrong",
                "redirect_uri": REDIRECT,
                "state": "abc.8765",
                "code_challenge": c,
                "code_challenge_method": "S256",
                "audience": AUDIENCE,
            },
        )
        assert r.status_code == 400
        assert b"client_id" in r.content

    def test_rejects_bad_redirect(self, api):
        _, c = _verifier_challenge()
        r = api.get(
            "/authorize",
            {
                "client_id": CLIENT_ID,
                "redirect_uri": "https://evil.example/callback",
                "state": "abc.8765",
                "code_challenge": c,
                "code_challenge_method": "S256",
                "audience": AUDIENCE,
            },
        )
        assert r.status_code == 400
        assert b"redirect_uri" in r.content

    def test_rejects_non_s256(self, api):
        _, c = _verifier_challenge()
        r = api.get(
            "/authorize",
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT,
                "state": "abc.8765",
                "code_challenge": c,
                "code_challenge_method": "plain",
                "audience": AUDIENCE,
            },
        )
        assert r.status_code == 400
        assert b"S256" in r.content

    def test_rejects_wrong_audience(self, api):
        _, c = _verifier_challenge()
        r = api.get(
            "/authorize",
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT,
                "state": "abc.8765",
                "code_challenge": c,
                "code_challenge_method": "S256",
                "audience": "https://api.openworker.com",
            },
        )
        assert r.status_code == 400
        assert b"audience" in r.content

    def test_renders_one9_signin(self, api):
        from coworker_cloud.models import AuthLoginSession

        _, c = _verifier_challenge()
        r = api.get(
            "/authorize",
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT,
                "state": "abc.8765",
                "code_challenge": c,
                "code_challenge_method": "S256",
                "audience": AUDIENCE,
            },
        )
        assert r.status_code == 200
        assert b"One9Founders Cloud" in r.content
        assert AuthLoginSession.objects.count() == 1


@pytest.mark.django_db
class TestPkceTokenExchange:
    def test_authorization_code_happy_path(self, api, user):
        verifier, challenge = _verifier_challenge()
        assert verify_s256(verifier, challenge)
        AuthorizationCode.objects.create(
            user=user,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT,
            code_challenge=challenge,
            code_challenge_method="S256",
            expires_at=timezone.now() + timedelta(minutes=5),
            code="test-auth-code",
        )
        r = api.post(
            "/oauth/token",
            {
                "grant_type": "authorization_code",
                "code": "test-auth-code",
                "redirect_uri": REDIRECT,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "Bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["expires_in"] > 0
        r2 = api.post(
            "/oauth/token",
            {
                "grant_type": "authorization_code",
                "code": "test-auth-code",
                "redirect_uri": REDIRECT,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            },
        )
        assert r2.status_code == 400


@pytest.mark.django_db
class TestAuthCallbackBounce:
    def test_bounces_to_port_in_state(self, api):
        r = api.get(
            "/v1/auth/callback",
            {"code": "c1", "state": "random.52341"},
        )
        assert r.status_code == 302
        assert r["Location"].startswith("http://127.0.0.1:52341/auth/callback?")
        assert "code=c1" in r["Location"]

    def test_invalid_port_falls_back(self, api):
        r = api.get("/v1/auth/callback", {"code": "c1", "state": "random.999999"})
        assert r.status_code == 302
        assert r["Location"].startswith("http://127.0.0.1:8765/auth/callback?")


def test_loopback_helpers():
    assert _loopback_port_from_state("x.4242") == 4242
    assert _loopback_port_from_state("no-port") == 8765
    assert _loopback_port_from_state("x.0") == 8765
    assert _is_loopback_oauth_callback("http://127.0.0.1:8765/oauth/callback")
    assert _is_loopback_oauth_callback("http://127.0.0.1:8765/oauth/callback/")
    assert not _is_loopback_oauth_callback("http://127.0.0.1:8765/evil")
    assert not _is_loopback_oauth_callback("https://127.0.0.1:8765/oauth/callback")
    assert not _is_loopback_oauth_callback("http://localhost:8765/oauth/callback")


@pytest.mark.django_db
class TestBrokerApi:
    def test_me_requires_auth(self, api):
        assert api.get("/v1/me").status_code == 401

    def test_me_returns_user(self, api, user, bearer):
        r = api.get("/v1/me", HTTP_AUTHORIZATION=f"Bearer {bearer}")
        assert r.status_code == 200
        body = r.json()["user"]
        assert body["email"] == "founder@example.com"
        assert body["user_id"] == f"one9_{user.id}"
        assert "Founder" in body["name"]

    def test_oauth_start_rejects_unsigned(self, api):
        r = api.post(
            "/v1/oauth/google/start",
            data=(
                '{"connector":"gmail",'
                '"redirect":"http://127.0.0.1:8765/oauth/callback","app_state":"s1"}'
            ),
            content_type="application/json",
        )
        assert r.status_code == 401

    def test_oauth_start_rejects_bad_redirect(self, api, bearer):
        r = api.post(
            "/v1/oauth/google/start",
            data=(
                '{"connector":"gmail",'
                '"redirect":"http://evil.com/oauth/callback","app_state":"s1"}'
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {bearer}",
        )
        assert r.status_code == 400
        assert "127.0.0.1" in r.json()["error"]

    def test_oauth_start_google_happy(self, api, bearer):
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "google-cid"}):
            r = api.post(
                "/v1/oauth/google/start",
                data=(
                    '{"connector":"gmail",'
                    '"redirect":"http://127.0.0.1:8765/oauth/callback",'
                    '"app_state":"s1"}'
                ),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        body = r.json()
        assert "accounts.google.com" in body["authorize_url"]
        assert body["app_state"] == "s1"
        assert ManagedOAuthPending.objects.count() == 1

    def test_telemetry_ack(self, api, bearer):
        r = api.post(
            "/v1/telemetry/events",
            data='{"events":[]}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {bearer}",
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_disconnect_clears_tokens(self, api, user, bearer):
        conn = CloudConnection.objects.create(
            user=user,
            provider="google",
            connector="gmail",
            status="connected",
            account="founder@example.com",
            refresh_token="secret-refresh",
            access_token="secret-access",
        )
        r = api.post(
            f"/v1/connections/{conn.id}/disconnect",
            HTTP_AUTHORIZATION=f"Bearer {bearer}",
        )
        assert r.status_code == 200
        conn.refresh_from_db()
        assert conn.status == "disconnected"
        assert conn.refresh_token == ""
        assert conn.access_token == ""

    @patch("requests.post")
    def test_oauth_refresh_happy(self, mock_post, api, user, bearer):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_resp
        conn = CloudConnection.objects.create(
            user=user,
            provider="google",
            connector="gmail",
            status="connected",
            refresh_token="old-refresh",
        )
        with patch.dict(
            "os.environ",
            {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "sec"},
        ):
            r = api.post(
                "/v1/oauth/google/refresh",
                data=f'{{"connection_id":"{conn.id}"}}',
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        assert r.json()["access_token"] == "new-access"
        conn.refresh_from_db()
        assert conn.access_token == "new-access"


class TestSimpleOAuthProviders:
    """Notion / Microsoft (Outlook) / HubSpot — the no-relay managed connectors."""

    def test_oauth_start_rejects_unknown_provider(self, api, bearer):
        r = api.post(
            "/v1/oauth/slack/start",
            data=(
                '{"connector":"slack",'
                '"redirect":"http://127.0.0.1:8765/oauth/callback","app_state":"s1"}'
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {bearer}",
        )
        assert r.status_code == 501

    def test_oauth_start_notion_happy(self, api, bearer):
        with patch.dict("os.environ", {"NOTION_CLIENT_ID": "notion-cid"}):
            r = api.post(
                "/v1/oauth/notion/start",
                data=(
                    '{"connector":"notion",'
                    '"redirect":"http://127.0.0.1:8765/oauth/callback",'
                    '"app_state":"s1"}'
                ),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        body = r.json()
        assert "api.notion.com/v1/oauth/authorize" in body["authorize_url"]
        assert "owner=user" in body["authorize_url"]
        assert ManagedOAuthPending.objects.count() == 1

    def test_oauth_start_microsoft_happy(self, api, bearer):
        with patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "ms-cid"}):
            r = api.post(
                "/v1/oauth/microsoft/start",
                data=(
                    '{"connector":"outlook",'
                    '"redirect":"http://127.0.0.1:8765/oauth/callback",'
                    '"app_state":"s1"}'
                ),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        assert "login.microsoftonline.com" in r.json()["authorize_url"]

    def test_oauth_start_hubspot_happy(self, api, bearer):
        with patch.dict("os.environ", {"HUBSPOT_CLIENT_ID": "hs-cid"}):
            r = api.post(
                "/v1/oauth/hubspot/start",
                data=(
                    '{"connector":"hubspot",'
                    '"redirect":"http://127.0.0.1:8765/oauth/callback",'
                    '"app_state":"s1"}'
                ),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        assert "app.hubspot.com/oauth/authorize" in r.json()["authorize_url"]

    @patch("requests.post")
    def test_notion_callback_uses_basic_auth_and_workspace_identity(
        self, mock_post, api, user
    ):
        pending = ManagedOAuthPending.objects.create(
            user=user,
            provider="notion",
            connector="notion",
            app_state="s1",
            sidecar_redirect="http://127.0.0.1:8765/oauth/callback",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "notion-token",
            "workspace_name": "Acme Workspace",
            "workspace_id": "ws_123",
            "owner": {"user": {"person": {"email": "founder@acme.com"}}},
        }
        mock_post.return_value = mock_resp

        with patch.dict(
            "os.environ",
            {"NOTION_CLIENT_ID": "cid", "NOTION_CLIENT_SECRET": "sec"},
        ):
            r = api.get(f"/v1/oauth/notion/callback?state={pending.id}&code=abc")

        assert r.status_code == 200
        # Basic auth (client_id, client_secret), no client_id/secret leaked into body.
        _, kwargs = mock_post.call_args
        assert kwargs["auth"] == ("cid", "sec")
        assert "client_id" not in kwargs["data"]
        conn = CloudConnection.objects.get(connector="notion")
        assert conn.account == "founder@acme.com"
        assert conn.account_id == "ws_123"
        assert conn.refresh_token == ""  # Notion tokens don't expire/refresh

    @patch("requests.get")
    @patch("requests.post")
    def test_microsoft_callback_resolves_identity_via_graph(
        self, mock_post, mock_get, api, user
    ):
        pending = ManagedOAuthPending.objects.create(
            user=user,
            provider="microsoft",
            connector="outlook",
            app_state="s1",
            sidecar_redirect="http://127.0.0.1:8765/oauth/callback",
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {
            "access_token": "ms-token",
            "refresh_token": "ms-refresh",
            "expires_in": 3600,
        }
        mock_post.return_value = token_resp
        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"mail": "founder@one9.com", "id": "aad-123"}
        mock_get.return_value = graph_resp

        with patch.dict(
            "os.environ",
            {"MICROSOFT_CLIENT_ID": "cid", "MICROSOFT_CLIENT_SECRET": "sec"},
        ):
            r = api.get(f"/v1/oauth/microsoft/callback?state={pending.id}&code=abc")

        assert r.status_code == 200
        # body auth (not basic) for Microsoft's token endpoint.
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["client_id"] == "cid"
        conn = CloudConnection.objects.get(connector="outlook")
        assert conn.account == "founder@one9.com"
        assert conn.account_id == "aad-123"
        assert conn.refresh_token == "ms-refresh"

    def test_hubspot_refresh_not_yet_connected_returns_404(self, api, bearer):
        r = api.post(
            "/v1/oauth/hubspot/refresh",
            data='{"connection_id":"00000000-0000-0000-0000-000000000000"}',
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {bearer}",
        )
        assert r.status_code == 404

    @patch("requests.post")
    def test_hubspot_refresh_happy(self, mock_post, api, user, bearer):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "hs-new-access",
            "refresh_token": "hs-new-refresh",
            "expires_in": 21600,
        }
        mock_post.return_value = mock_resp
        conn = CloudConnection.objects.create(
            user=user,
            provider="hubspot",
            connector="hubspot",
            status="connected",
            refresh_token="hs-old-refresh",
        )
        with patch.dict(
            "os.environ",
            {"HUBSPOT_CLIENT_ID": "cid", "HUBSPOT_CLIENT_SECRET": "sec"},
        ):
            r = api.post(
                "/v1/oauth/hubspot/refresh",
                data=f'{{"connection_id":"{conn.id}"}}',
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {bearer}",
            )
        assert r.status_code == 200
        assert r.json()["access_token"] == "hs-new-access"
        conn.refresh_from_db()
        assert conn.refresh_token == "hs-new-refresh"


class TestWindowsWorkerDownload:
    def test_landing_page(self, api):
        r = api.get("/openworker/")
        assert r.status_code == 200
        assert b"One9 Worker for Windows" in r.content
        assert b"One9Founders Cloud" in r.content
        assert b"/v1/openworker/download/windows" in r.content

    def test_releases_json(self, api):
        r = api.get("/v1/openworker/releases")
        assert r.status_code == 200
        body = r.json()
        assert body["cloud"] == "One9Founders Cloud"
        assert body["windows"]["filename"] == "One9Worker-Setup.exe"
        assert body["windows"]["url"].endswith("/v1/openworker/download/windows")

    def test_download_serves_local_exe(self, api, settings, tmp_path):
        settings.OPENWORKER_LOCAL_DOWNLOAD_DIR = tmp_path
        settings.OPENWORKER_WINDOWS_FILENAME = "One9Worker-Setup.exe"
        exe = tmp_path / "One9Worker-Setup.exe"
        exe.write_bytes(b"MZ-fake-installer")
        r = api.get("/v1/openworker/download/windows")
        assert r.status_code == 200
        assert r["Content-Disposition"].startswith("attachment;")
        assert b"MZ-fake-installer" in b"".join(r.streaming_content)

    def test_download_redirects_when_url_configured(self, api, settings, tmp_path):
        settings.OPENWORKER_LOCAL_DOWNLOAD_DIR = tmp_path
        settings.OPENWORKER_WINDOWS_DOWNLOAD_URL = (
            "https://files.one9founders.com/openworker/windows/One9Worker-Setup.exe"
        )
        r = api.get("/v1/openworker/download/windows")
        assert r.status_code in (301, 302)
        assert r["Location"].endswith("One9Worker-Setup.exe")

    def test_download_404_in_debug_without_file(self, api, settings, tmp_path):
        settings.DEBUG = True
        settings.OPENWORKER_LOCAL_DOWNLOAD_DIR = tmp_path
        settings.OPENWORKER_WINDOWS_DOWNLOAD_URL = ""
        r = api.get("/v1/openworker/download/windows")
        assert r.status_code == 404

