from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.discovery.facts import Facts
from api.discovery.quality_gate import passes_quality_gate, similarity_ratio
from api.discovery.sources import (
    dedupe_candidates,
    fetch_product_hunt_candidates,
    fetch_taaft_candidates,
    normalize_name,
    normalize_url,
)
from api.models import ExternalToolCandidate, ToolSource
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


class TestExternalSources:
    def test_product_hunt_uses_feed_as_source_without_detail_url(self):
        entry = {
            "title": "Demo AI — Write faster",
            "summary": "An AI writing assistant",
            "link": "https://www.producthunt.com/posts/demo-ai",
        }
        with patch(
            "api.discovery.sources.feedparser.parse",
            return_value=SimpleNamespace(entries=[entry]),
        ):
            candidates = fetch_product_hunt_candidates()

        assert candidates == [
            {
                "name": "Demo AI",
                "url": "",
                "sourceUrl": "https://www.producthunt.com/posts/demo-ai",
                "officialUrl": "",
                "externalId": "demo-ai",
                "sourceType": "producthunt",
                "rawSignal": {
                    "upvotes": 0,
                    "title": "Demo AI — Write faster",
                    "summary": "An AI writing assistant",
                },
            }
        ]

    def test_taaft_reads_only_robots_allowed_public_pages(self):
        listing = Mock()
        listing.text = '<a href="/ai/demo-ai/">Demo AI</a>'
        listing.raise_for_status.return_value = None
        detail = Mock()
        detail.text = (
            '<meta name="description" content="A demo assistant">'
            '<a href="https://demo.example" rel="nofollow">Open website</a>'
        )
        detail.raise_for_status.return_value = None

        with (
            patch("api.discovery.sources._robots_allows", return_value=True) as allowed,
            patch(
                "api.discovery.sources.requests.get",
                side_effect=[listing, detail],
            ),
        ):
            candidates = fetch_taaft_candidates(limit=1)

        assert allowed.call_count == 2
        assert candidates[0]["sourceType"] == "taaft"
        assert candidates[0]["sourceUrl"] == (
            "https://theresanaiforthat.com/ai/demo-ai/"
        )
        assert candidates[0]["officialUrl"] == "https://demo.example"

    def test_taaft_stops_when_robots_disallows_listing(self):
        with (
            patch("api.discovery.sources._robots_allows", return_value=False),
            patch("api.discovery.sources.requests.get") as request,
        ):
            assert fetch_taaft_candidates() == []
        request.assert_not_called()


@pytest.mark.django_db
class TestCandidateReview:
    def test_stage_is_idempotent_and_refreshes_payload(self):
        from api.discovery.pipeline import stage_external_candidate

        candidate = {
            "name": "Demo",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/demo",
            "rawSignal": {"upvotes": 1},
        }
        first, created = stage_external_candidate(candidate)
        candidate["rawSignal"]["upvotes"] = 2
        second, created_again = stage_external_candidate(candidate)

        assert created is True
        assert created_again is False
        assert first.pk == second.pk
        assert second.payload["upvotes"] == 2
        assert ExternalToolCandidate.objects.count() == 1

    def test_review_source_is_staged_without_fetching_detail(self, settings):
        from api.discovery.pipeline import run_new_tool_discovery

        settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES = set()
        candidate = {
            "name": "Demo",
            "url": "",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/demo",
            "rawSignal": {"summary": "AI demo"},
        }
        with patch("api.discovery.pipeline.process_candidate") as process:
            result = run_new_tool_discovery(candidates=[candidate], max_new=10)

        process.assert_not_called()
        assert result["staged"] == 1
        assert result["by_source"] == {"producthunt": {"staged": 1}}

    def test_approval_links_existing_tool_and_publishes_source(self):
        from api.discovery.pipeline import approve_external_candidate

        tool = ToolFactory(name="Demo Tool", website="https://demo.example")
        candidate = ExternalToolCandidate.objects.create(
            source="producthunt",
            source_url="https://www.producthunt.com/posts/demo-tool",
            official_url="https://www.demo.example/",
            external_id="demo-tool",
            name="Demo Tool",
            payload={"summary": "Demo"},
        )

        result = approve_external_candidate(candidate)

        candidate.refresh_from_db()
        assert result == tool
        assert candidate.status == ExternalToolCandidate.STATUS_PUBLISHED
        assert candidate.linked_tool == tool
        reference = ToolSource.objects.get(tool=tool)
        assert reference.source == "producthunt"
        assert reference.url == candidate.source_url

    def test_tool_api_exposes_attribution_but_not_raw_payload(self):
        tool = ToolFactory()
        ToolSource.objects.create(
            tool=tool,
            source="g2",
            label="G2",
            url="https://www.g2.com/products/example",
        )
        ExternalToolCandidate.objects.create(
            source="taaft",
            source_url="https://theresanaiforthat.com/ai/example/",
            name=tool.name,
            payload={"private": "source snippet"},
            linked_tool=tool,
        )

        response = APIClient().get(reverse("tool-detail", kwargs={"slug": tool.slug}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sources"][0]["source"] == "g2"
        assert "payload" not in response.data
        assert "source snippet" not in str(response.data)


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
