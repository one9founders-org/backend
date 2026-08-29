from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.discovery.facts import Facts
from api.discovery.quality_gate import passes_quality_gate, similarity_ratio
from api.discovery.sources import (
    dedupe_candidates,
    normalize_name,
    normalize_url,
)
from tests.factories import ToolFactory


class TestNormalize:
    def test_normalize_url_strips_protocol_www_slash(self):
        assert normalize_url("https://www.Example.com/app/") == "example.com/app"
        assert normalize_url("http://example.com") == "example.com"

    def test_normalize_name_strips_suffixes(self):
        assert normalize_name("Cursor AI") == "cursor"
        assert normalize_name("Notion App") == "notion"


class TestQualityGate:
    def test_rejects_short_and_similar_and_missing_fields(self):
        facts = Facts(pricing=None, category=None)
        source = "This tool helps teams write better marketing copy with AI assistants."
        generated = source
        passed, reasons = passes_quality_gate("Demo", generated, facts, source)
        assert passed is False
        assert any("word count" in reason for reason in reasons)
        assert any("similar" in reason for reason in reasons)
        assert any("pricing and category" in reason for reason in reasons)

    def test_accepts_original_text_with_a_structured_field(self):
        facts = Facts(pricing="freemium", category=None)
        generated = (
            "Demo is a writing workspace for small product teams. It drafts "
            "briefs from notes, keeps a shared outline, and exports to docs "
            "without claiming to replace an editor. Founders use it for weekly "
            "updates and launch copy."
        )
        source = "The #1 AI copywriter trusted by 10,000 marketers worldwide!!!"
        passed, reasons = passes_quality_gate("Demo", generated, facts, source)
        assert passed is True
        assert reasons == []
        assert similarity_ratio(generated, source) <= 0.35


@pytest.mark.django_db
class TestDedupe:
    def test_drops_existing_url_and_name_and_self_dupes(self):
        ToolFactory(name="Cursor AI", website="https://www.cursor.com/")
        candidates = [
            {
                "name": "Cursor",
                "url": "https://cursor.com",
                "sourceType": "github",
                "rawSignal": {"stars": 10},
            },
            {
                "name": "Brand New Tool",
                "url": "https://brand-new.example",
                "sourceType": "hackernews",
                "rawSignal": {"points": 5},
            },
            {
                "name": "Brand New Tool AI",
                "url": "https://www.brand-new.example/",
                "sourceType": "producthunt",
                "rawSignal": {"upvotes": 1},
            },
        ]
        result = dedupe_candidates(candidates)
        assert len(result) == 1
        assert result[0]["name"] == "Brand New Tool"


@pytest.mark.django_db
class TestPublishNewTool:
    def test_github_candidate_gets_open_source_track(self):
        from api.discovery.facts import Facts
        from api.discovery.pipeline import publish_new_tool
        from api.hygiene.track import OPEN_SOURCE

        description = (
            "LangChain is an open-source framework for building LLM apps. "
            "Teams chain prompts, tools, and memory into production agents "
            "without locking into a single hosted vendor."
        )
        tool = publish_new_tool(
            {
                "name": "github/langchain-ai/langchain",
                "url": "https://github.com/langchain-ai/langchain",
                "generated": description,
                "facts": Facts(pricing="free", topics=["llm", "agents"]),
            }
        )
        assert tool.track == OPEN_SOURCE
        assert tool.name == "github/langchain-ai/langchain"


@pytest.mark.django_db
class TestDiscoveryTrigger:
    def test_forbidden_without_secret(self):
        client = APIClient()
        url = reverse("run-discovery-trigger")
        response = client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_forbidden_with_wrong_secret(self, settings):
        settings.DISCOVERY_TRIGGER_SECRET = "expected-secret"
        client = APIClient()
        url = reverse("run-discovery-trigger")
        response = client.post(url, HTTP_X_TRIGGER_SECRET="wrong")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_valid_secret_runs_jobs(self, settings):
        settings.DISCOVERY_TRIGGER_SECRET = "expected-secret"
        client = APIClient()
        url = reverse("run-discovery-trigger")
        with (
            patch(
                "api.discovery.views.run_new_tool_discovery",
                return_value={"published": 0},
            ) as discover,
            patch(
                "api.discovery.views.run_refresh_descriptions",
                return_value={"updated": 0},
            ) as refresh,
        ):
            response = client.post(url, HTTP_X_TRIGGER_SECRET="expected-secret")
        assert response.status_code == status.HTTP_200_OK
        discover.assert_called_once()
        refresh.assert_called_once()
        assert "discovery" in response.data
        assert "refresh" in response.data

    def test_job_query_runs_only_refresh(self, settings):
        settings.DISCOVERY_TRIGGER_SECRET = "expected-secret"
        client = APIClient()
        url = reverse("run-discovery-trigger")
        with (
            patch("api.discovery.views.run_new_tool_discovery") as discover,
            patch(
                "api.discovery.views.run_refresh_descriptions",
                return_value={"updated": 1},
            ) as refresh,
        ):
            response = client.post(
                f"{url}?job=refresh",
                HTTP_X_TRIGGER_SECRET="expected-secret",
            )
        assert response.status_code == status.HTTP_200_OK
        discover.assert_not_called()
        refresh.assert_called_once()
