from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from api.ai_enrichment import EnrichmentError, chat_model, enrich_tool_data
from api.models import ToolSubmission
from api.submission_enrichment import enrich_submission


@override_settings(TOOL_ENRICH_MODEL="gpt-4.1", HYGIENE_ENRICH_MODEL="gpt-4o-mini")
def test_chat_model_prefers_tool_enrich_setting():
    assert chat_model() == "gpt-4.1"


def test_default_chat_model_is_gpt_4_1():
    from django.conf import settings

    from api import ai_enrichment

    assert ai_enrichment.DEFAULT_CHAT_MODEL == "gpt-4.1"
    # Production default when TOOL_ENRICH_MODEL env is unset.
    assert settings.TOOL_ENRICH_MODEL == "gpt-4.1"


@override_settings(OPENAI_API_KEY="")
def test_enrich_requires_api_key():
    with pytest.raises(EnrichmentError, match="OPENAI_API_KEY"):
        enrich_tool_data("Acme", "Writes copy", "https://acme.example")


@override_settings(OPENAI_API_KEY="sk-test", TOOL_ENRICH_MODEL="gpt-4.1")
def test_enrich_uses_configured_model_and_json_object_format():
    payload = {
        "short_description": "Writes product copy",
        "tags": ["writing"],
        "use_cases": ["Landing pages"],
        "features": ["Brief to draft"],
        "categories": ["Writing"],
        "pricing_models": ["freemium"],
        "pricing_tiers": [{"name": "Free", "price": 0, "billing": "monthly"}],
        "pricing_from": 0,
        "platforms": ["web"],
        "integrations": [],
        "startup_benefits": "Faster drafts",
        "ideal_for": ["founders"],
        "startup_friendly": True,
        "free_tier_available": True,
        "free_trial_days": None,
    }
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(
            message=MagicMock(
                content="```json\n" + __import__("json").dumps(payload) + "\n```"
            )
        )
    ]
    create = MagicMock(return_value=fake_response)

    with patch("api.ai_enrichment.OpenAI") as openai_cls:
        openai_cls.return_value.chat.completions.create = create
        data = enrich_tool_data("Acme", "Writes product copy", "https://acme.example")

    assert data["short_description"] == "Writes product copy"
    assert data["tags"] == ["writing"]
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "gpt-4.1"
    assert kwargs["response_format"] == {"type": "json_object"}


@override_settings(OPENAI_API_KEY="sk-test", TOOL_ENRICH_MODEL="gpt-4.1")
def test_enrich_surfaces_deprecated_model_errors():
    with patch("api.ai_enrichment.OpenAI") as openai_cls:
        openai_cls.return_value.chat.completions.create.side_effect = Exception(
            "The model `gpt-3.5-turbo` has been deprecated"
        )
        with pytest.raises(EnrichmentError, match="deprecated"):
            enrich_tool_data("Acme", "Writes copy", "https://acme.example")


@pytest.mark.django_db
@override_settings(OPENAI_API_KEY="sk-test", TOOL_ENRICH_MODEL="gpt-4.1")
def test_failed_submission_stores_real_model_error():
    submission = ToolSubmission.objects.create(
        name="Broken Enrich",
        description="A tool whose enrichment should record the OpenAI error.",
        website="https://example.com/broken-enrich",
        submitter_email="founder@example.com",
        submitter_name="Founder",
        enrichment_status="pending",
    )
    with patch("api.ai_enrichment.OpenAI") as openai_cls:
        openai_cls.return_value.chat.completions.create.side_effect = Exception(
            "The model `gpt-3.5-turbo` has been deprecated"
        )
        enrich_submission(submission.pk)

    submission.refresh_from_db()
    assert submission.enrichment_status == "failed"
    assert "deprecated" in submission.enrichment_error
    assert submission.enrichment_attempts == 1
