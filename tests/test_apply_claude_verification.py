import json

import pytest
from django.core.management import call_command

from api.models import Tool
from tests.factories import ToolFactory


def _draft(**overrides):
    record = {
        "exists": True,
        "official_url": "https://acme.example/",
        "company": "Acme",
        "status": "active",
        "short_description": "Writes product copy for founders",
        "description": "Acme writes product copy for founders from a short brief.",
        "pricing_type": "freemium",
        "pricing_summary": "Free and Pro.",
        "pricing_source_url": "https://acme.example/pricing",
        "free_tier": True,
        "features": ["Brief to draft"],
        "use_cases": ["Draft a homepage"],
        "integrations": ["Slack"],
        "confidence": 0.8,
        "notes": "",
    }
    record.update(overrides.pop("record", {}))
    payload = {
        "slug": "acme",
        "name": "Acme",
        "listed_website": "https://affiliate.example/acme",
        "record": record,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_apply_updates_an_existing_listing(tmp_path):
    tool = ToolFactory(
        name="Acme",
        slug="acme",
        description="Old description that should be replaced.",
        short_description="Old blurb",
        website="https://affiliate.example/acme",
        pricing_type="paid",
        free_tier_available=False,
        tags=["productivity"],
    )
    path = tmp_path / "drafts.jsonl"
    path.write_text(json.dumps(_draft()) + "\n", encoding="utf-8")

    call_command("apply_claude_verification", f"--file={path}", "--apply")

    tool.refresh_from_db()
    assert tool.short_description == "Writes product copy for founders"
    assert tool.description.startswith("Acme writes product copy")
    assert tool.website == "https://acme.example/"
    assert tool.pricing_type == "freemium"
    assert tool.free_tier_available is True
    assert tool.features == ["Brief to draft"]
    assert tool.last_enriched_at is not None


@pytest.mark.django_db
def test_low_confidence_and_verified_rows_are_left_alone(tmp_path):
    low = ToolFactory(
        name="Low",
        slug="low",
        description="Keep this.",
        short_description="Keep",
        tags=["productivity"],
    )
    verified = ToolFactory(
        name="Checked",
        slug="checked",
        description="Hand checked.",
        short_description="Hand",
        verified=True,
        tags=["productivity"],
    )
    path = tmp_path / "drafts.jsonl"
    lines = [
        _draft(slug="low", name="Low", record={"confidence": 0.4}),
        _draft(
            slug="checked",
            name="Checked",
            record={"short_description": "Should not land", "description": "Nope."},
        ),
    ]
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )

    call_command("apply_claude_verification", f"--file={path}", "--apply")

    low.refresh_from_db()
    verified.refresh_from_db()
    assert low.description == "Keep this."
    assert verified.short_description == "Hand"
    assert Tool.objects.filter(slug="low").count() == 1
