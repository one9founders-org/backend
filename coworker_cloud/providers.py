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
