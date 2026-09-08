from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from api.ai_enrichment import sanitize_enriched
from api.verified_listings import (
    CLAUDE_FIELDS,
    claude_is_stale,
    overlay_verified_listing,
)
from tests.factories import ToolFactory


def _stale_claude(**kwargs):
    defaults = dict(
        name="Claude",
        slug="claude",
        short_description="Claude is an AI chat assistant.",
        free_trial_days=14,
        pricing_from=Decimal("0.00"),
        pricing_models=["freemium", "paid", "trial"],
        pricing_tiers=[
            {"name": "Opus 4.5", "price": 0, "billing": "monthly"},
            {"name": "Sonnet 4.5", "price": 20, "billing": "monthly"},
        ],
        integrations=["tool1", "tool2"],
        free_tier_available=True,
        tags=["Chat Assistant"],
    )
    defaults.update(kwargs)
    return ToolFactory(**defaults)


class TestSanitizeEnriched:
    def test_drops_placeholder_integrations_and_null_trial(self):
        cleaned = sanitize_enriched(
            {
                "integrations": ["tool1", "tool2", "Slack"],
                "free_trial_days": 14,
                "pricing_models": ["freemium", "paid", "trial"],
            }
        )
        assert cleaned["integrations"] == ["Slack"]
        assert cleaned["free_trial_days"] == 14
        assert "trial" in cleaned["pricing_models"]

    def test_null_trial_strips_trial_pricing_model(self):
        cleaned = sanitize_enriched(
            {
                "free_trial_days": None,
                "pricing_models": ["freemium", "trial"],
                "integrations": ["tool1"],
            }
        )
        assert cleaned["free_trial_days"] is None
        assert cleaned["pricing_models"] == ["freemium"]
        assert cleaned["integrations"] == []

    def test_prompt_no_longer_defaults_to_a_14_day_trial(self):
        from api import ai_enrichment

        source = open(ai_enrichment.__file__).read()
        assert '"free_trial_days": 14' not in source
        assert '"free_trial_days": null' in source
        assert "Do not invent a trial length" in source


class TestClaudeStaleDetection:
    def test_stale_enrichment_row(self):
        tool = SimpleNamespace(
            free_trial_days=14,
            pricing_models=["freemium", "paid", "trial"],
            pricing_tiers=[{"name": "Opus 4.5", "price": 0}],
            integrations=["tool1", "tool2"],
            pricing_from=Decimal("0.00"),
        )
        assert claude_is_stale(tool) is True

    def test_current_row_is_not_stale(self):
        tool = SimpleNamespace(
            free_trial_days=None,
            pricing_models=["freemium", "paid"],
            pricing_tiers=CLAUDE_FIELDS["pricing_tiers"],
            integrations=["Slack", "GitHub"],
            pricing_from=Decimal("20.00"),
        )
        assert claude_is_stale(tool) is False

    def test_overlay_rewrites_trial_and_price(self):
        tool = SimpleNamespace(
            slug="claude",
            gst_applicable=True,
            **{
                "free_trial_days": 14,
                "pricing_models": ["trial"],
                "pricing_tiers": [{"name": "Opus 4.5"}],
                "integrations": ["tool1", "tool2"],
                "pricing_from": Decimal("0.00"),
            },
        )
        data = overlay_verified_listing(
            tool,
            {
                "free_trial_days": 14,
                "pricing_from": "0.00",
                "pricing_models": ["trial"],
                "pricing_inr": None,
                "gst_applicable": True,
            },
        )
        assert data["free_trial_days"] is None
        assert data["pricing_from"] == "20.00"
        assert data["pricing_inr"] == 1670
        assert data["pricing_inr_with_gst"] == 1971
        assert "trial" not in data["pricing_models"]


@pytest.mark.django_db
class TestClaudeListingAPI:
    def test_retrieve_hides_fake_14_day_trial(self):
        _stale_claude()
        client = APIClient()
        response = client.get(reverse("tool-detail", kwargs={"slug": "claude"}))
        assert response.status_code == 200
        assert response.data["free_trial_days"] is None
        assert response.data["pricing_from"] == "20.00"
        assert response.data["free_tier_available"] is True
        assert "trial" not in response.data["pricing_models"]
        tier_names = [t["name"] for t in response.data["pricing_tiers"]]
        assert "Pro" in tier_names
        assert "Opus 4.5" not in tier_names
        assert response.data["integrations"] == [
            "Google Drive",
            "Gmail",
            "Slack",
            "GitHub",
            "MCP",
        ]
        sources = {t.get("source") for t in response.data["pricing_tiers"]}
        assert (
            "https://support.claude.com/en/articles/11049762-choose-a-claude-plan"
            in sources
        )

    def test_other_tools_keep_a_real_14_day_trial(self):
        ToolFactory(
            name="Other SaaS",
            slug="other-saas",
            free_trial_days=14,
            pricing_from=Decimal("29.00"),
            tags=["crm"],
        )
        client = APIClient()
        response = client.get(reverse("tool-detail", kwargs={"slug": "other-saas"}))
        assert response.data["free_trial_days"] == 14
        assert response.data["pricing_from"] == "29.00"


@pytest.mark.django_db
class TestCorrectVerifiedListingsCommand:
    def test_dry_run_does_not_write(self):
        tool = _stale_claude()
        out = StringIO()
        call_command("correct_verified_listings", stdout=out)
        tool.refresh_from_db()
        assert tool.free_trial_days == 14
        assert "DRY-RUN" in out.getvalue()

    def test_apply_clears_trial_and_sets_pro_price(self):
        tool = _stale_claude()
        call_command("correct_verified_listings", "--apply")
        tool.refresh_from_db()
        assert tool.free_trial_days is None
        assert tool.pricing_from == Decimal("20.00")
        assert "trial" not in tool.pricing_models
        assert tool.integrations[0] == "Google Drive"
        assert tool.pricing_tiers[1]["name"] == "Pro"
