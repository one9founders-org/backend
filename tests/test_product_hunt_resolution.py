from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from api.discovery.product_hunt_resolution import (
    ProductHuntURLResolution,
    resolve_product_hunt_url,
)
from api.models import ExternalToolCandidate


def test_resolver_accepts_exact_product_domain():
    with patch(
        "api.discovery.product_hunt_resolution.firecrawl.search",
        return_value=[
            {
                "url": "https://www.worklifepanda.com/pricing",
                "title": "Work Life Panda — AI career assistant",
                "description": "An AI assistant for managing work and life.",
            },
            {
                "url": "https://example.com/work-life-panda-review",
                "title": "Work Life Panda review",
                "description": "Review of an AI assistant.",
            },
        ],
    ):
        result = resolve_product_hunt_url("Work Life Panda")

    assert result is not None
    assert result.url == "https://www.worklifepanda.com"
    assert result.confidence == 0.99


def test_resolver_rejects_ambiguous_domains():
    with patch(
        "api.discovery.product_hunt_resolution.firecrawl.search",
        return_value=[
            {
                "url": "https://demo.ai",
                "title": "Demo AI",
                "description": "AI assistant.",
            },
            {
                "url": "https://demo.com",
                "title": "Demo AI",
                "description": "AI assistant.",
            },
        ],
    ):
        assert resolve_product_hunt_url("Demo AI") is None


def test_resolver_rejects_product_hunt_and_weak_matches():
    with patch(
        "api.discovery.product_hunt_resolution.firecrawl.search",
        return_value=[
            {
                "url": "https://www.producthunt.com/posts/demo-ai",
                "title": "Demo AI",
                "description": "AI assistant.",
            },
            {
                "url": "https://unrelated.example",
                "title": "Unrelated product",
                "description": "AI assistant.",
            },
        ],
    ):
        assert resolve_product_hunt_url("Demo AI") is None


@pytest.mark.django_db
def test_command_resets_resolved_error_candidate_to_pending(settings):
    settings.FIRECRAWL_API_KEY = "test-key"
    candidate = ExternalToolCandidate.objects.create(
        source="producthunt",
        source_url="https://www.producthunt.com/posts/demo",
        name="Demo AI",
        payload={"summary": "AI research assistant"},
        status=ExternalToolCandidate.STATUS_ERROR,
        review_notes="Resolve an official website before approval",
    )
    resolution = ProductHuntURLResolution(
        url="https://demo.example",
        confidence=0.99,
        query='"Demo AI" AI tool official website',
        title="Demo AI",
        reason="normalized product name matches the domain",
    )

    with patch(
        "api.management.commands.resolve_product_hunt_urls." "resolve_product_hunt_url",
        return_value=resolution,
    ):
        call_command("resolve_product_hunt_urls", stdout=StringIO())

    candidate.refresh_from_db()
    assert candidate.official_url == "https://demo.example"
    assert candidate.status == ExternalToolCandidate.STATUS_PENDING
    assert candidate.payload["official_resolution"]["provider"] == "firecrawl_search"
    assert candidate.payload["official_resolution"]["confidence"] == 0.99
    assert "Review the domain" in candidate.review_notes


@pytest.mark.django_db
def test_command_dry_run_does_not_update_candidate(settings):
    settings.FIRECRAWL_API_KEY = "test-key"
    candidate = ExternalToolCandidate.objects.create(
        source="producthunt",
        source_url="https://www.producthunt.com/posts/demo",
        name="Demo AI",
        status=ExternalToolCandidate.STATUS_ERROR,
    )
    resolution = ProductHuntURLResolution(
        url="https://demo.example",
        confidence=0.99,
        query='"Demo AI" AI tool official website',
        title="Demo AI",
        reason="normalized product name matches the domain",
    )

    with patch(
        "api.management.commands.resolve_product_hunt_urls." "resolve_product_hunt_url",
        return_value=resolution,
    ):
        call_command("resolve_product_hunt_urls", "--dry-run", stdout=StringIO())

    candidate.refresh_from_db()
    assert candidate.official_url == ""
    assert candidate.status == ExternalToolCandidate.STATUS_ERROR
