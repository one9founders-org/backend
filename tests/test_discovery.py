from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.discovery.facts import Facts
from api.discovery.quality_gate import passes_quality_gate, similarity_ratio
from api.discovery.sources import dedupe_candidates, normalize_name, normalize_url
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


class TestGitHubDiscoveryExpansion:
    def test_seed_list_includes_reticle(self):
        from api.discovery.sources import GITHUB_SEED_REPOS

        assert "reticlehq/reticle" in GITHUB_SEED_REPOS

    def test_star_queries_target_user_facing_tools(self):
        from api.discovery.github_queries import GITHUB_STAR_QUERIES

        blob = " ".join(GITHUB_STAR_QUERIES).lower()
        assert "stars:>=" in blob
        assert "fork:false" in blob
        assert "llm-tools" in blob or "mcp-server" in blob
        assert "reticle" in blob

    def test_candidate_skips_forks_and_archived(self):
        from api.discovery.sources import _candidate_from_github_item

        assert (
            _candidate_from_github_item(
                {
                    "html_url": "https://github.com/acme/forked",
                    "full_name": "acme/forked",
                    "fork": True,
                    "stargazers_count": 999,
                }
            )
            is None
        )
        assert (
            _candidate_from_github_item(
                {
                    "html_url": "https://github.com/acme/old",
                    "full_name": "acme/old",
                    "archived": True,
                    "stargazers_count": 999,
                }
            )
            is None
        )

    def test_fetch_github_candidates_merges_stars_search_and_seeds(self, settings):
        from api.discovery.sources import fetch_github_candidates

        settings.GITHUB_TOKEN = "gh-test"
        search_item = {
            "html_url": "https://github.com/acme/new-llm-tool",
            "full_name": "acme/new-llm-tool",
            "name": "new-llm-tool",
            "description": "A new LLM helper",
            "stargazers_count": 12,
            "pushed_at": "2026-09-01T00:00:00Z",
            "topics": ["llm"],
            "fork": False,
            "archived": False,
        }
        starred_item = {
            "html_url": "https://github.com/acme/popular-mcp",
            "full_name": "acme/popular-mcp",
            "name": "popular-mcp",
            "description": "Popular MCP server",
            "stargazers_count": 5000,
            "pushed_at": "2026-08-01T00:00:00Z",
            "topics": ["mcp-server"],
            "fork": False,
            "archived": False,
            "license": {"spdx_id": "MIT"},
        }
        seed_item = {
            "html_url": "https://github.com/reticlehq/reticle",
            "full_name": "reticlehq/reticle",
            "name": "reticle",
            "description": "Verify running web apps from the inside",
            "stargazers_count": 900,
            "pushed_at": "2026-09-10T00:00:00Z",
            "topics": ["devtools"],
            "fork": False,
            "archived": False,
            "license": {"spdx_id": "Apache-2.0"},
        }

        def _fake_search(query, *, headers, per_page=50):
            if "stars:>=" in query or query.startswith("topic:mcp"):
                return [starred_item]
            return [search_item]

        with (
            patch(
                "api.discovery.sources._github_search",
                side_effect=_fake_search,
            ) as search,
            patch(
                "api.discovery.sources._github_repo",
                side_effect=lambda full_name, headers: (
                    seed_item if full_name == "reticlehq/reticle" else None
                ),
            ),
        ):
            rows = fetch_github_candidates(days=30)

        urls = {r["url"] for r in rows}
        assert "https://github.com/reticlehq/reticle" in urls
        assert "https://github.com/acme/new-llm-tool" in urls
        assert "https://github.com/acme/popular-mcp" in urls
        assert rows[0]["url"] == "https://github.com/acme/popular-mcp"
        assert search.call_count >= 1
        queries = [
            call.kwargs.get("q") or call.args[0] for call in search.call_args_list
        ]
        assert any("stars:>=" in q for q in queries)
        assert any("pushed:>" in q for q in queries)
        assert any("created:>" in q for q in queries)
        assert any("fork:false" in q for q in queries)


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
