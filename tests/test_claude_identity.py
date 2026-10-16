from unittest.mock import Mock, patch

import pytest
from botocore.credentials import ReadOnlyCredentials
from django.test import override_settings

from api.claude_identity import (
    ANTHROPIC_AUDIENCE,
    ClaudeIdentityError,
    federation_configured,
    federation_resources,
    get_anthropic_client,
    request_web_identity_token,
    role_arn,
)


@pytest.mark.django_db
class TestClaudeIdentity:
    def test_role_arn_uses_the_backend_role_name(self):
        assert (
            role_arn("123456789012")
            == "arn:aws:iam::123456789012:role/one9founders-claude-wif"
        )

    def test_federation_requires_rule_org_and_service_account(self):
        with override_settings(
            ANTHROPIC_FEDERATION_RULE_ID="",
            ANTHROPIC_ORGANIZATION_ID="org",
            ANTHROPIC_SERVICE_ACCOUNT_ID="svac",
        ):
            assert federation_configured() is False
        with override_settings(
            ANTHROPIC_FEDERATION_RULE_ID="fdrl_test",
            ANTHROPIC_ORGANIZATION_ID="org",
            ANTHROPIC_SERVICE_ACCOUNT_ID="svac_test",
        ):
            assert federation_configured() is True

    def test_resources_pin_the_role_and_audience(self):
        bodies = federation_resources(
            "https://example.tokens.sts.global.api.aws",
            "arn:aws:iam::123456789012:role/one9founders-claude-wif",
        )
        assert bodies["issuer"]["name"] == "one9founders-backend"
        assert bodies["issuer"]["jwks"] == {"type": "discovery"}
        assert bodies["rule"]["match"] == {
            "subject_prefix": "arn:aws:iam::123456789012:role/one9founders-claude-wif",
            "audience": ANTHROPIC_AUDIENCE,
        }
        assert bodies["rule"]["oauth_scope"] == "workspace:developer"
        assert bodies["rule"]["applies_to_all_workspaces"] is True

    @override_settings(
        ANTHROPIC_FEDERATION_RULE_ID="fdrl_test",
        ANTHROPIC_ORGANIZATION_ID="00000000-0000-0000-0000-000000000000",
        ANTHROPIC_SERVICE_ACCOUNT_ID="svac_test",
        ANTHROPIC_WORKSPACE_ID="",
        ANTHROPIC_API_KEY="sk-ant-static",
    )
    def test_client_uses_federation_even_when_api_key_is_set(self):
        with (
            patch("anthropic.Anthropic") as client_cls,
            patch("anthropic.WorkloadIdentityCredentials") as credentials_cls,
        ):
            get_anthropic_client()
        credentials_cls.assert_called_once()
        kwargs = credentials_cls.call_args.kwargs
        assert kwargs["federation_rule_id"] == "fdrl_test"
        assert kwargs["identity_token_provider"].__name__ == "fetch_web_identity_token"
        assert "api_key" not in client_cls.call_args.kwargs
        assert (
            client_cls.call_args.kwargs["credentials"] is credentials_cls.return_value
        )

    @override_settings(
        ANTHROPIC_FEDERATION_RULE_ID="",
        ANTHROPIC_ORGANIZATION_ID="",
        ANTHROPIC_SERVICE_ACCOUNT_ID="",
        ANTHROPIC_API_KEY="sk-ant-static",
    )
    def test_client_falls_back_to_the_static_key(self):
        with patch("anthropic.Anthropic") as client_cls:
            get_anthropic_client()
        assert client_cls.call_args.kwargs == {"api_key": "sk-ant-static"}

    def test_sts_request_asks_for_the_anthropic_audience(self):
        captured = {}

        def fake_post(url, data=None, headers=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            response = Mock()
            response.status_code = 200
            response.text = (
                "<GetWebIdentityTokenResponse>"
                "<GetWebIdentityTokenResult>"
                "<WebIdentityToken>header.payload.sig</WebIdentityToken>"
                "</GetWebIdentityTokenResult>"
                "</GetWebIdentityTokenResponse>"
            )
            return response

        credentials = ReadOnlyCredentials("AKIDEXAMPLE", "secret", "session")
        with patch("api.claude_identity.requests.post", side_effect=fake_post):
            token = request_web_identity_token(credentials, "us-east-1")
        assert token == "header.payload.sig"
        assert captured["url"] == "https://sts.us-east-1.amazonaws.com/"
        assert "Audience.member.1=https%3A%2F%2Fapi.anthropic.com" in captured["data"]
        assert "SigningAlgorithm=RS256" in captured["data"]
        assert "Authorization" in captured["headers"]

    def test_issuer_lookup_reads_the_identifier_field(self):
        from api.management.commands.claude_federation import _issuer_url

        info = {
            "IssuerIdentifier": "https://example.tokens.sts.global.api.aws",
            "JwtVendingEnabled": True,
        }
        client = Mock()
        client.get_outbound_web_identity_federation_info.return_value = info
        with patch("boto3.client", return_value=client):
            assert _issuer_url() == info["IssuerIdentifier"]

    def test_sts_error_does_not_include_the_request_token(self):
        response = Mock()
        response.status_code = 403
        response.text = "<Error><Code>AccessDenied</Code><Message>no</Message></Error>"
        credentials = ReadOnlyCredentials("AKIDEXAMPLE", "secret", "session-token")
        with patch("api.claude_identity.requests.post", return_value=response):
            with pytest.raises(ClaudeIdentityError) as exc:
                request_web_identity_token(credentials, "us-east-1")
        assert "AccessDenied" in str(exc.value)
        assert "session-token" not in str(exc.value)
