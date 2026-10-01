"""Claude API auth through AWS IAM outbound identity federation.

The backend EC2 role calls STS GetWebIdentityToken. The Anthropic SDK
exchanges that JWT for a short-lived access token. A static
ANTHROPIC_API_KEY is used only when federation settings are absent, so a
leftover key cannot shadow the instance role.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import InstanceMetadataFetcher, InstanceMetadataProvider
from django.conf import settings

ANTHROPIC_AUDIENCE = "https://api.anthropic.com"
INSTANCE_ROLE_NAME = "one9founders-claude-wif"
ISSUER_NAME = "aws-sts-one9"
SERVICE_ACCOUNT_NAME = "one9founders-backend"
FEDERATION_RULE_NAME = "one9founders-backend"
TOKEN_SECONDS = 900


class ClaudeIdentityError(RuntimeError):
    """Raised when federation settings or the STS exchange cannot proceed."""


def federation_configured() -> bool:
    return bool(
        _setting("ANTHROPIC_FEDERATION_RULE_ID")
        and _setting("ANTHROPIC_ORGANIZATION_ID")
        and _setting("ANTHROPIC_SERVICE_ACCOUNT_ID")
    )


def role_arn(account_id: str) -> str:
    account = str(account_id).strip()
    if not account.isdigit():
        raise ClaudeIdentityError("AWS account id is missing")
    return f"arn:aws:iam::{account}:role/{INSTANCE_ROLE_NAME}"


def get_anthropic_client():
    """Return an Anthropic client. Federation wins over a static API key."""
    from anthropic import Anthropic, WorkloadIdentityCredentials

    if federation_configured():
        workspace_id = _setting("ANTHROPIC_WORKSPACE_ID") or None
        return Anthropic(
            credentials=WorkloadIdentityCredentials(
                identity_token_provider=fetch_web_identity_token,
                federation_rule_id=_setting("ANTHROPIC_FEDERATION_RULE_ID"),
                organization_id=_setting("ANTHROPIC_ORGANIZATION_ID"),
                service_account_id=_setting("ANTHROPIC_SERVICE_ACCOUNT_ID"),
                workspace_id=workspace_id,
            )
        )

    api_key = _setting("ANTHROPIC_API_KEY")
    if not api_key:
        raise ClaudeIdentityError(
            "Set ANTHROPIC_FEDERATION_RULE_ID, ANTHROPIC_ORGANIZATION_ID, and "
            "ANTHROPIC_SERVICE_ACCOUNT_ID, or set ANTHROPIC_API_KEY for local "
            "development."
        )
    return Anthropic(api_key=api_key)


def fetch_web_identity_token() -> str:
    """Mint a fresh STS web identity token for https://api.anthropic.com."""
    return request_web_identity_token(
        instance_role_credentials(),
        region=_setting("ANTHROPIC_STS_REGION") or "us-east-1",
    )


def instance_role_credentials():
    """Load the EC2 instance role, ignoring static keys in the environment."""
    provider = InstanceMetadataProvider(
        iam_role_fetcher=InstanceMetadataFetcher(timeout=2, num_attempts=2)
    )
    credentials = provider.load()
    if credentials is None:
        raise ClaudeIdentityError(
            "No EC2 instance role is available. Attach the "
            f"{INSTANCE_ROLE_NAME} instance profile."
        )
    return credentials.get_frozen_credentials()


def request_web_identity_token(credentials, region: str) -> str:
    body = urlencode(
        {
            "Action": "GetWebIdentityToken",
            "Version": "2011-06-15",
            "Audience.member.1": ANTHROPIC_AUDIENCE,
            "SigningAlgorithm": "RS256",
            "DurationSeconds": str(TOKEN_SECONDS),
        }
    )
    url = f"https://sts.{region}.amazonaws.com/"
    request = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    SigV4Auth(credentials, "sts", region).add_auth(request)
    prepared = request.prepare()
    response = requests.post(
        prepared.url,
        data=prepared.body,
        headers=dict(prepared.headers),
        timeout=10,
    )
    if response.status_code >= 400:
        code = _xml_text(response.text, "Code") or str(response.status_code)
        message = (
            _xml_text(response.text, "Message") or "STS GetWebIdentityToken failed"
        )
        raise ClaudeIdentityError(f"{code}: {message[:300]}")
    token = _xml_text(response.text, "WebIdentityToken")
    if not token:
        raise ClaudeIdentityError("STS did not return a web identity token")
    return token


def federation_resources(issuer_url: str, subject: str, workspace_id: str = "") -> dict:
    """Bodies for the Claude Console / Admin API federation resources."""
    issuer = issuer_url.strip().rstrip("/")
    if not issuer.startswith("https://"):
        raise ClaudeIdentityError("STS issuer URL must be https")
    rule = {
        "name": FEDERATION_RULE_NAME,
        "match": {
            "subject_prefix": subject,
            "audience": ANTHROPIC_AUDIENCE,
        },
        "target": {"type": "service_account"},
        "oauth_scope": "workspace:developer",
        "token_lifetime_seconds": 600,
    }
    if workspace_id:
        rule["workspace_id"] = workspace_id
    else:
        rule["applies_to_all_workspaces"] = True
    return {
        "service_account": {
            "name": SERVICE_ACCOUNT_NAME,
            "organization_role": "developer",
        },
        "issuer": {
            "name": ISSUER_NAME,
            "issuer_url": issuer,
            "jwks": {"type": "discovery"},
        },
        "rule": rule,
    }


def _setting(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _xml_text(payload: str, tag: str) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return ""
    for element in root.iter():
        if element.tag == tag or element.tag.endswith("}" + tag):
            return (element.text or "").strip()
    return ""
