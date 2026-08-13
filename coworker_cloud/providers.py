"""Provider → Google/Slack OAuth scope maps for managed one-click connect."""

from __future__ import annotations

# connector id → OAuth provider key (mirrors openworker coworker/cloud.py)
PROVIDER_FOR_CONNECTOR = {
    "gmail": "google",
    "google_calendar": "google",
    "google_drive": "google",
    "slack": "slack",
    "notion": "notion",
    "github": "github",
    "hubspot": "hubspot",
    "outlook": "microsoft",
}

GOOGLE_SCOPES = {
    "gmail": [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "google_calendar": [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar",
    ],
    "google_drive": [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/drive.readonly",
    ],
}

# Account login (One9 Cloud sign-in) — identity only, no Gmail scopes.
LOGIN_SCOPES = ["openid", "email", "profile"]

# Simple (no-relay) managed OAuth providers: one token exchange, no inbound
# infra needed — unlike Slack/GitHub, which need a WebSocket relay for the
# bot to receive events (out of scope here; see docs/COWORKER_CLOUD.md).
#
# token_auth: "body" -> client_id/secret in the token POST body
#             (Google/Microsoft/HubSpot shape). "basic" -> HTTP Basic auth
#             with client_id:client_secret (Notion's documented shape).
# refresh: whether the provider issues a refresh_token (Notion's integration
#          tokens don't expire).
OAUTH_PROVIDER_CONFIG = {
    "notion": {
        "connector": "notion",
        "authorize_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "client_id_env": "NOTION_CLIENT_ID",
        "client_secret_env": "NOTION_CLIENT_SECRET",
        "token_auth": "basic",
        "scopes": [],  # Notion grants exactly what the integration is configured for.
        "extra_authorize_params": {"owner": "user"},
        "refresh": False,
    },
    "microsoft": {
        "connector": "outlook",
        "authorize_url": (
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        ),
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "client_id_env": "MICROSOFT_CLIENT_ID",
        "client_secret_env": "MICROSOFT_CLIENT_SECRET",
        "token_auth": "body",
        "scopes": [
            "offline_access",
            "openid",
            "email",
            "profile",
            "https://graph.microsoft.com/Mail.ReadWrite",
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/Calendars.ReadWrite",
        ],
        "extra_authorize_params": {},
        "refresh": True,
    },
    "hubspot": {
        "connector": "hubspot",
        "authorize_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "client_id_env": "HUBSPOT_CLIENT_ID",
        "client_secret_env": "HUBSPOT_CLIENT_SECRET",
        "token_auth": "body",
        "scopes": [
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.companies.read",
            "crm.objects.deals.read",
        ],
        "extra_authorize_params": {},
        "refresh": True,
    },
}
