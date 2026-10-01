"""Print, or register, Claude workload identity for the backend role."""

import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.claude_identity import (
    ANTHROPIC_AUDIENCE,
    ClaudeIdentityError,
    federation_configured,
    federation_resources,
    role_arn,
)

ADMIN_API = "https://api.anthropic.com/v1/organizations"


class Command(BaseCommand):
    help = (
        "Show the AWS issuer and role ARN to register for Claude workload "
        "identity. Pass --register with an org:admin ANTHROPIC_AUTH_TOKEN "
        "to create the service account, issuer, and rule."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--register",
            action="store_true",
            help="Create the Anthropic federation resources with ANTHROPIC_AUTH_TOKEN.",
        )
        parser.add_argument(
            "--issuer-url",
            default="",
            help="STS issuer URL. Looked up from IAM when omitted.",
        )
        parser.add_argument(
            "--workspace-id",
            default="",
            help="Workspace to enable the rule for. Defaults to every workspace.",
        )

    def handle(self, *args, **options):
        try:
            issuer_url = options["issuer_url"].strip() or _issuer_url()
            subject = role_arn(_account_id())
        except ClaudeIdentityError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"issuer_url={issuer_url}")
        self.stdout.write(f"subject={subject}")
        self.stdout.write(f"audience={ANTHROPIC_AUDIENCE}")
        self.stdout.write(
            "federation_configured=" + ("yes" if federation_configured() else "no")
        )
        if not options["register"]:
            self.stdout.write(
                "In the Claude Console open Settings → Workload identity → "
                "Connect workload → AWS, and match this issuer, subject, and "
                "audience. Then set ANTHROPIC_FEDERATION_RULE_ID, "
                "ANTHROPIC_ORGANIZATION_ID, and ANTHROPIC_SERVICE_ACCOUNT_ID. "
                "Unset ANTHROPIC_API_KEY after the first federated call works. "
                "Re-run with --register if you have an org:admin token."
            )
            return

        token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
        if not token:
            raise CommandError(
                "ANTHROPIC_AUTH_TOKEN from `ant auth login --scope org:admin` "
                "is required. A static API key cannot create federation resources."
            )
        workspace_id = (
            options["workspace_id"].strip() or settings.ANTHROPIC_WORKSPACE_ID
        )
        try:
            created = _register(token, issuer_url, subject, workspace_id)
        except ClaudeIdentityError as exc:
            raise CommandError(str(exc)) from exc
        for key in (
            "ANTHROPIC_ORGANIZATION_ID",
            "ANTHROPIC_SERVICE_ACCOUNT_ID",
            "ANTHROPIC_FEDERATION_RULE_ID",
        ):
            self.stdout.write(f"{key}={created[key]}")


def _issuer_url() -> str:
    import boto3

    try:
        info = boto3.client("iam").get_outbound_web_identity_federation_info()
    except Exception as exc:
        raise ClaudeIdentityError(
            "Could not read the STS issuer URL. Pass --issuer-url. "
            f"({type(exc).__name__})"
        ) from exc
    issuer = str(info.get("IssuerIdentifier") or info.get("IssuerUrl") or "").strip()
    if not issuer:
        raise ClaudeIdentityError("IAM did not return an outbound issuer URL")
    return issuer


def _account_id() -> str:
    import boto3

    try:
        account = boto3.client("sts").get_caller_identity()["Account"]
    except Exception as exc:
        raise ClaudeIdentityError(
            f"Could not read the AWS account id ({type(exc).__name__})"
        ) from exc
    return str(account)


def _register(token: str, issuer_url: str, subject: str, workspace_id: str) -> dict:
    bodies = federation_resources(issuer_url, subject, workspace_id)
    headers = {
        "authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    service_account = _create_or_reuse(
        headers,
        "/service_accounts",
        bodies["service_account"],
        bodies["service_account"]["name"],
    )
    issuer = _create_or_reuse(
        headers,
        "/federation_issuers",
        bodies["issuer"],
        bodies["issuer"]["name"],
    )
    rule_body = dict(bodies["rule"])
    rule_body["issuer_id"] = issuer["id"]
    rule_body["target"] = {
        "type": "service_account",
        "service_account_id": service_account["id"],
    }
    rule = _create_or_reuse(
        headers,
        "/federation_rules",
        rule_body,
        rule_body["name"],
    )
    return {
        "ANTHROPIC_ORGANIZATION_ID": str(
            service_account.get("organization_id")
            or issuer.get("organization_id")
            or ""
        ),
        "ANTHROPIC_SERVICE_ACCOUNT_ID": service_account["id"],
        "ANTHROPIC_FEDERATION_RULE_ID": rule["id"],
    }


def _create_or_reuse(headers: dict, path: str, body: dict, name: str) -> dict:
    response = requests.post(ADMIN_API + path, headers=headers, json=body, timeout=30)
    if response.status_code == 409:
        existing = _find_by_name(headers, path, name)
        if existing:
            return existing
    if response.status_code >= 400:
        raise ClaudeIdentityError(
            f"{path} failed ({response.status_code}): {_safe_error(response)}"
        )
    payload = response.json()
    if not payload.get("id"):
        raise ClaudeIdentityError(f"{path} did not return an id")
    return payload


def _find_by_name(headers: dict, path: str, name: str) -> dict | None:
    response = requests.get(
        ADMIN_API + path, headers=headers, params={"limit": 100}, timeout=30
    )
    if response.status_code >= 400:
        raise ClaudeIdentityError(
            f"list {path} failed ({response.status_code}): {_safe_error(response)}"
        )
    payload = response.json()
    rows = payload.get("data") or payload.get("items") or []
    for row in rows:
        if row.get("name") == name:
            return row
    return None


def _safe_error(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:180]
    if isinstance(body, dict):
        for key in ("error", "message", "detail", "type"):
            if body.get(key):
                return str(body[key])[:180]
    return response.text[:180]
