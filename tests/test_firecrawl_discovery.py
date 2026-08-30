"""Tests for Firecrawl India/new-tool discovery and directory columns."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.discovery.facts import Facts
from api.discovery.india_sources import (
    fetch_india_tool_candidates,
    fetch_new_tool_candidates,
)
from api.discovery.pipeline import publish_new_tool
from api.hygiene.track import AI_TOOL, OPEN_SOURCE
from tests.factories import CategoryFactory, ToolFactory


@pytest.fixture
def api_client():
    return APIClient()


class TestFirecrawlClientGuards:
    def test_search_noop_without_key(self, settings):
        from api.discovery import firecrawl

        settings.FIRECRAWL_API_KEY = ""
        assert firecrawl.search("Indian AI tools") == []

    def test_scrape_noop_without_key(self, settings):
        from api.discovery import firecrawl

        settings.FIRECRAWL_API_KEY = ""
        assert firecrawl.scrape_tool_page("https://example.com") == {}


class TestIndiaSources:
    def test_india_search_builds_candidates(self, settings):
        settings.FIRECRAWL_API_KEY = "fc-test"
        with patch(
            "api.discovery.india_sources.firecrawl.search",
            return_value=[
                {
                    "url": "https://sarvam.ai",
                    "title": "Sarvam AI",
                    "description": "Indian language AI",
                },
                {
                    "url": "https://producthunt.com/posts/foo",
                    "title": "Listicle",
                    "description": "skip me",
                },
            ],
        ):
            rows = fetch_india_tool_candidates(limit_per_query=2)
        urls = {r["url"] for r in rows}
        assert "https://sarvam.ai" in urls
        assert all(r["sourceType"] == "firecrawl_india" for r in rows)
        assert all(r["rawSignal"]["india_focus"] for r in rows)
        assert "https://producthunt.com/posts/foo" not in urls

    def test_new_tools_search(self, settings):
        settings.FIRECRAWL_API_KEY = "fc-test"
        with patch(
            "api.discovery.india_sources.firecrawl.search",
            return_value=[
                {
                    "url": "https://newtool.dev",
                    "title": "NewTool",
                    "description": "just launched",
                }
            ],
        ):
            rows = fetch_new_tool_candidates(limit_per_query=1)
        assert rows
        assert rows[0]["sourceType"] == "firecrawl_new"


@pytest.mark.django_db
class TestPublishFromFirecrawlFacts:
    def test_publishes_logo_pricing_categories_india_and_track(self):
        CategoryFactory(name="Writing", slug="writing")
        description = (
            "Sarvam is an Indian language AI platform for founders. It offers "
            "speech and text models with INR pricing so Indian startups can "
            "ship bilingual products without paying USD-only SaaS rates."
        )
        tool = publish_new_tool(
            {
                "name": "Sarvam AI",
                "url": "https://sarvam.ai",
                "generated": description,
                "candidate": {
                    "sourceType": "firecrawl_india",
                    "rawSignal": {"india_focus": True},
                },
                "facts": Facts(
                    title="Sarvam AI",
                    meta_description="Indian language AI",
                    pricing="freemium",
                    category="Writing",
                    categories=["Writing"],
                    logo_url="https://sarvam.ai/logo.png",
                    pricing_from=19.0,
                    free_tier_available=True,
                    india_focused=True,
                    has_india_pricing=True,
                    source_text="Indian language AI",
                ),
            }
        )
        assert tool.logo_url == "https://sarvam.ai/logo.png"
        assert tool.pricing_type == "freemium"
        assert tool.free_tier_available is True
        assert tool.pricing_from == Decimal("19.0")
        assert tool.pricing_has_india_plan is True
        assert "india" in tool.tags
        assert tool.track == AI_TOOL
        assert tool.categories.filter(name="Writing").exists()

    def test_github_extract_buckets_open_source(self):
        description = (
            "OpenDev is a free coding agent you self-host. Clone the GitHub "
            "repo, run docker compose, and automate pull requests without a "
            "hosted SaaS bill for your founding engineering team."
        )
        tool = publish_new_tool(
            {
                "name": "github/acme/opendev",
                "url": "https://github.com/acme/opendev",
                "generated": description,
                "candidate": {"sourceType": "firecrawl_new", "rawSignal": {}},
                "facts": Facts(
                    title="OpenDev",
                    pricing="free",
                    github_url="https://github.com/acme/opendev",
                    free_tier_available=True,
                    source_text="self-host coding agent",
                ),
            }
        )
        assert tool.track == OPEN_SOURCE


@pytest.mark.django_db
class TestDirectoryColumnsAPI:
    def test_returns_two_primary_columns(self, api_client):
        ToolFactory(
            name="HostedWriter",
            track=AI_TOOL,
            is_active=True,
            short_description="Hosted",
            description="Hosted writing tool for founders.",
        )
        ToolFactory(
            name="github/acme/oss",
            website="https://github.com/acme/oss",
            track=OPEN_SOURCE,
            is_active=True,
            short_description="OSS",
            description="Open source repo for founders.",
        )

        response = api_client.get(reverse("tool-directory-columns"))
        assert response.status_code == status.HTTP_200_OK
        columns = response.data["columns"]
        assert len(columns) == 2
        assert columns[0]["track"] == AI_TOOL
        assert columns[1]["track"] == OPEN_SOURCE
        assert columns[0]["list_path"] == "/api/tools/?track=ai_tool"
        assert columns[1]["list_path"] == "/api/tools/?track=open_source"
        names0 = {t["name"] for t in columns[0]["tools"]}
        names1 = {t["name"] for t in columns[1]["tools"]}
        assert "HostedWriter" in names0
        assert "github/acme/oss" in names1


@pytest.mark.django_db
class TestIndiaFilter:
    def test_india_query_param(self, api_client):
        ToolFactory(
            name="IndiaTool",
            tags=["auto-discovery", "india"],
            pricing_has_india_plan=True,
            is_active=True,
            description="An Indian AI tool for founders with local pricing.",
            short_description="Indian AI",
        )
        ToolFactory(
            name="GlobalTool",
            tags=["auto-discovery"],
            is_active=True,
            description="A global AI tool without India focus for comparison.",
            short_description="Global AI",
        )
        response = api_client.get(reverse("tool-list"), {"india": "true"})
        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data["results"]]
        assert "IndiaTool" in names
        assert "GlobalTool" not in names


@pytest.mark.django_db
class TestIndiaDiscoveryTrigger:
    def test_india_job(self, settings):
        settings.DISCOVERY_TRIGGER_SECRET = "expected-secret"
        client = APIClient()
        url = reverse("run-discovery-trigger")
        with patch(
            "api.discovery.views.run_india_and_new_discovery",
            return_value={"published": 2},
        ) as india:
            response = client.post(
                f"{url}?job=india",
                HTTP_X_TRIGGER_SECRET="expected-secret",
            )
        assert response.status_code == status.HTTP_200_OK
        india.assert_called_once()
        assert response.data["india"]["published"] == 2
