from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.discovery.facts import Facts, _fetch_html_facts
from api.discovery.quality_gate import passes_quality_gate, similarity_ratio
from api.discovery.sources import (
    _resolve_product_hunt_redirect,
    dedupe_candidates,
    fetch_all_candidates,
    fetch_product_hunt_api_candidates,
    fetch_product_hunt_candidates,
    fetch_product_hunt_rss_candidates,
    fetch_taaft_candidates,
    normalize_name,
    normalize_url,
)
from api.models import ExternalToolCandidate, ToolFact, ToolSource
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
    def test_product_hunt_redirect_requires_normal_redirect_response(self):
        response = Mock(
            status_code=302,
            headers={"Location": "https://demo.example/product"},
        )
        with patch("api.discovery.sources.requests.get", return_value=response):
            assert (
                _resolve_product_hunt_redirect("https://www.producthunt.com/r/p/demo")
                == "https://demo.example/product"
            )

        blocked = Mock(status_code=403, headers={})
        with patch("api.discovery.sources.requests.get", return_value=blocked):
            assert (
                _resolve_product_hunt_redirect("https://www.producthunt.com/r/p/demo")
                == ""
            )

    def test_product_hunt_uses_feed_as_source_without_detail_url(self):
        entry = {
            "title": "Demo AI — Write faster",
            "link": "https://www.producthunt.com/posts/demo-ai",
            "id": "tag:www.producthunt.com,2005:Post/123",
            "published": "2026-09-12T01:00:00Z",
            "updated": "2026-09-12T02:00:00Z",
            "author": "Demo Maker",
            "content": [
                {
                    "value": (
                        "<p>An AI writing assistant</p>"
                        '<a href="https://www.producthunt.com/r/p/123">Link</a>'
                    )
                }
            ],
        }
        with (
            patch(
                "api.discovery.sources.feedparser.parse",
                return_value=SimpleNamespace(entries=[entry]),
            ),
            patch(
                "api.discovery.sources._resolve_product_hunt_redirect",
                return_value="",
            ) as resolve,
        ):
            candidates = fetch_product_hunt_rss_candidates()

        resolve.assert_called_once_with("https://www.producthunt.com/r/p/123")
        assert candidates[0]["name"] == "Demo AI — Write faster"
        assert candidates[0]["sourceUrl"] == (
            "https://www.producthunt.com/posts/demo-ai"
        )
        assert candidates[0]["externalId"] == "123"
        assert candidates[0]["officialUrl"] == ""
        assert candidates[0]["rawSignal"] == {
            "upvotes": 0,
            "summary": "An AI writing assistant",
            "published_at": "2026-09-12T01:00:00Z",
            "updated_at": "2026-09-12T02:00:00Z",
            "author": "Demo Maker",
            "logo_url": "",
            "outbound_url": "https://www.producthunt.com/r/p/123",
        }

    def test_product_hunt_does_not_treat_ai_inside_a_word_as_ai_signal(self):
        entry = {
            "title": "Captain Switch",
            "link": "https://www.producthunt.com/posts/captain-switch",
            "summary": "Manage emergency shutdown procedures",
        }
        with patch(
            "api.discovery.sources.feedparser.parse",
            return_value=SimpleNamespace(entries=[entry]),
        ):
            assert fetch_product_hunt_rss_candidates() == []

    def test_product_hunt_api_maps_authorized_structured_fields(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                "id": "123",
                                "name": "Demo AI",
                                "tagline": "AI writing assistant",
                                "description": "Draft startup updates with AI",
                                "url": "https://www.producthunt.com/products/demo-ai",
                                "website": "https://demo.example",
                                "votesCount": 42,
                                "createdAt": "2026-09-12T01:00:00Z",
                                "thumbnail": {"url": "https://img.example/demo.png"},
                            }
                        }
                    ]
                },
            }
        }
        with patch("api.discovery.sources.requests.post", return_value=response):
            candidates = fetch_product_hunt_api_candidates("approved-token")

        assert candidates[0]["officialUrl"] == "https://demo.example"
        assert candidates[0]["rawSignal"]["upvotes"] == 42
        assert candidates[0]["rawSignal"]["logo_url"] == (
            "https://img.example/demo.png"
        )

    def test_product_hunt_api_falls_back_to_rss_when_unavailable(self, settings):
        settings.PRODUCT_HUNT_API_TOKEN = "approved-token"
        with (
            patch(
                "api.discovery.sources.fetch_product_hunt_api_candidates",
                return_value=[],
            ),
            patch(
                "api.discovery.sources.fetch_product_hunt_rss_candidates",
                return_value=[{"name": "RSS Demo"}],
            ) as rss,
        ):
            assert fetch_product_hunt_candidates() == [{"name": "RSS Demo"}]
        rss.assert_called_once_with()

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

    def test_one_source_failure_does_not_abort_other_sources(self, settings):
        settings.TAAFT_DISCOVERY_ENABLED = False
        product_hunt = {
            "name": "Demo",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/demo",
        }

        def failing_source(**_kwargs):
            raise RuntimeError("rate limited")

        with (
            patch(
                "api.discovery.sources.fetch_github_candidates",
                new=failing_source,
            ),
            patch(
                "api.discovery.sources.fetch_gitlab_candidates",
                return_value=[],
            ),
            patch(
                "api.discovery.sources.fetch_codeberg_candidates",
                return_value=[],
            ),
            patch(
                "api.discovery.sources.fetch_product_hunt_candidates",
                return_value=[product_hunt],
            ),
            patch(
                "api.discovery.sources.fetch_hacker_news_candidates", return_value=[]
            ),
        ):
            assert fetch_all_candidates() == [product_hunt]


class TestFirstPartyFacts:
    def test_crawls_allowed_same_host_pricing_and_tracks_provenance(self):
        homepage = Mock(
            url="https://demo.example/",
            text=(
                '<meta name="description" content="AI research workspace">'
                '<a href="/pricing">Pricing</a>'
                '<a href="/login">Log in</a>'
                '<a href="https://other.example/pricing">External pricing</a>'
            ),
        )
        homepage.raise_for_status.return_value = None
        pricing = Mock(
            url="https://demo.example/pricing",
            text="<main>Free plan forever. Pro starts at $12 per month.</main>",
        )
        pricing.raise_for_status.return_value = None

        with (
            patch(
                "api.discovery.sources._robots_allows",
                side_effect=lambda url: "/login" not in url,
            ) as robots,
            patch(
                "api.discovery.facts.requests.get",
                side_effect=[homepage, pricing],
            ) as request,
        ):
            facts = _fetch_html_facts("https://demo.example/")

        assert request.call_count == 2
        assert robots.call_count == 2
        assert facts.pricing == "paid"
        assert facts.pricing_from == 12
        assert facts.free_tier_available is True
        assert facts.evidence_urls["pricing"] == "https://demo.example/pricing"
        assert facts.field_sources["pricing_from_usd"] == "https://demo.example/pricing"

    def test_does_not_fetch_robots_disallowed_first_party_page(self):
        homepage = Mock(
            url="https://demo.example/",
            text='<a href="/pricing">Pricing</a>',
        )
        homepage.raise_for_status.return_value = None

        with (
            patch(
                "api.discovery.sources._robots_allows",
                side_effect=[True, False],
            ),
            patch(
                "api.discovery.facts.requests.get",
                return_value=homepage,
            ) as request,
        ):
            facts = _fetch_html_facts("https://demo.example/")

        request.assert_called_once()
        assert "pricing" not in facts.evidence_urls

    def test_rejects_cross_host_redirect_from_official_page(self):
        homepage = Mock(
            url="https://login-provider.example/challenge",
            text="<p>Challenge</p>",
        )
        homepage.raise_for_status.return_value = None
        with (
            patch("api.discovery.sources._robots_allows", return_value=True),
            patch("api.discovery.facts.requests.get", return_value=homepage),
        ):
            assert _fetch_html_facts("https://demo.example/") == Facts()


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

    def test_review_sources_stage_even_when_outranked_by_github_cap(self, settings):
        """Product Hunt must not lose to GitHub stars under max_new."""
        from api.discovery.pipeline import run_new_tool_discovery

        settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES = set()
        github_a = {
            "name": "Huge Stars",
            "url": "https://github.com/example/huge-stars",
            "sourceType": "github",
            "sourceUrl": "https://github.com/example/huge-stars",
            "rawSignal": {"stars": 50000},
        }
        github_b = {
            "name": "Also Huge",
            "url": "https://github.com/example/also-huge",
            "sourceType": "github",
            "sourceUrl": "https://github.com/example/also-huge",
            "rawSignal": {"stars": 40000},
        }
        producthunt = {
            "name": "Quiet Launch",
            "url": "",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/quiet-launch",
            "rawSignal": {"upvotes": 3},
        }
        with patch("api.discovery.pipeline.process_candidate") as process:
            process.return_value = {
                "passed": False,
                "reasons": ["skipped in test"],
                "candidate": github_a,
            }
            result = run_new_tool_discovery(
                candidates=[github_a, github_b, producthunt],
                max_new=1,
            )

        assert result["staged"] == 1
        assert result["by_source"]["producthunt"] == {"staged": 1}
        assert ExternalToolCandidate.objects.filter(
            source="producthunt",
            source_url="https://www.producthunt.com/posts/quiet-launch",
        ).exists()
        # Cap still applies to auto-publish sources (GitHub).
        assert process.call_count == 1
        assert result["deferred_over_cap"] == 1
        assert result["rejected"] == 1

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

    def test_failed_approval_records_error_for_review(self):
        from api.discovery.pipeline import approve_external_candidate

        candidate = ExternalToolCandidate.objects.create(
            source="producthunt",
            source_url="https://www.producthunt.com/posts/unresolved-demo",
            name="Unresolved Demo",
        )

        with pytest.raises(ValueError, match="official website"):
            approve_external_candidate(candidate)

        candidate.refresh_from_db()
        assert candidate.status == ExternalToolCandidate.STATUS_ERROR
        assert "official website" in candidate.review_notes

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

        with (
            patch(
                "api.views.ToolViewSet.get_queryset",
                return_value=tool.__class__.objects.filter(pk=tool.pk).prefetch_related(
                    "categories", "source_references"
                ),
            ),
            patch("api.serializers.CategorySerializer.get_tool_count", return_value=1),
        ):
            response = APIClient().get(
                reverse("tool-detail", kwargs={"slug": tool.slug})
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sources"][0]["source"] == "g2"
        assert "payload" not in response.data
        assert "source snippet" not in str(response.data)

    def test_anonymous_user_cannot_mutate_candidate_in_admin(self):
        candidate = ExternalToolCandidate.objects.create(
            source="producthunt",
            source_url="https://www.producthunt.com/posts/private-demo",
            name="Private Demo",
        )

        response = APIClient().post(
            reverse("admin:api_externaltoolcandidate_changelist"),
            {"action": "reject_candidates", "_selected_action": [candidate.pk]},
        )

        candidate.refresh_from_db()
        assert response.status_code == status.HTTP_302_FOUND
        assert "/admin/login/" in response["Location"]
        assert candidate.status == ExternalToolCandidate.STATUS_PENDING


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

    def test_persists_first_party_facts_with_observed_source(self):
        from api.discovery.pipeline import publish_new_tool

        tool = publish_new_tool(
            {
                "name": "Sourced Demo",
                "url": "https://sourced-demo.example",
                "generated": (
                    "Sourced Demo helps founders organize product research and "
                    "turn verified notes into concise launch briefs for their teams."
                ),
                "facts": Facts(
                    meta_description="Official product research workspace",
                    pricing="freemium",
                    pricing_from=12,
                    free_tier_available=True,
                    evidence_urls={
                        "homepage": "https://sourced-demo.example",
                        "pricing": "https://sourced-demo.example/pricing",
                    },
                    field_sources={
                        "pricing_type": "https://sourced-demo.example/pricing",
                        "pricing_from_usd": "https://sourced-demo.example/pricing",
                        "free_tier_available": ("https://sourced-demo.example/pricing"),
                    },
                ),
                "candidate": {
                    "name": "Sourced Demo",
                    "sourceType": "producthunt",
                    "sourceUrl": "https://www.producthunt.com/products/sourced-demo",
                    "externalId": "123",
                },
            }
        )

        assert ToolSource.objects.filter(tool=tool, source="official").exists()
        assert ToolSource.objects.filter(tool=tool, source="producthunt").exists()
        pricing = ToolFact.objects.get(tool=tool, field_name="pricing_from_usd")
        assert pricing.value == 12
        assert str(pricing.confidence) == "0.95"
        assert pricing.source_url == "https://sourced-demo.example/pricing"
        evidence = ToolFact.objects.get(
            tool=tool,
            field_name="source_document_pricing",
        )
        assert evidence.value["type"] == "pricing"
        assert evidence.source_url == "https://sourced-demo.example/pricing"


@pytest.mark.django_db
class TestProductHuntCommand:
    def test_dry_run_reports_resolution_without_database_writes(self):
        candidates = [
            {
                "name": "Resolved",
                "sourceType": "producthunt",
                "sourceUrl": "https://www.producthunt.com/posts/resolved",
                "officialUrl": "https://resolved.example",
            },
            {
                "name": "Review",
                "sourceType": "producthunt",
                "sourceUrl": "https://www.producthunt.com/posts/review",
                "officialUrl": "",
            },
        ]
        output = StringIO()
        with (
            patch(
                "api.management.commands.discover_product_hunt."
                "fetch_product_hunt_candidates",
                return_value=candidates,
            ),
            patch(
                "api.management.commands.discover_product_hunt.dedupe_candidates",
                side_effect=lambda items: items,
            ),
        ):
            call_command("discover_product_hunt", "--dry-run", stdout=output)

        assert "Candidates: 2" in output.getvalue()
        assert "Official websites resolved: 1" in output.getvalue()
        assert ExternalToolCandidate.objects.count() == 0

    def test_default_command_stages_candidates_without_auto_publish(self, settings):
        settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES = set()
        candidate = {
            "name": "Demo",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/demo",
            "officialUrl": "https://demo.example",
            "rawSignal": {"summary": "AI assistant"},
        }
        with (
            patch(
                "api.management.commands.discover_product_hunt."
                "fetch_product_hunt_candidates",
                return_value=[candidate],
            ),
            patch(
                "api.management.commands.discover_product_hunt.dedupe_candidates",
                side_effect=lambda items: items,
            ),
            patch("api.discovery.pipeline.process_candidate") as process,
        ):
            call_command("discover_product_hunt")

        process.assert_not_called()
        staged = ExternalToolCandidate.objects.get()
        assert staged.status == ExternalToolCandidate.STATUS_PENDING

    def test_auto_publish_must_be_explicit(self, settings):
        settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES = set()
        candidate = {
            "name": "Demo",
            "sourceType": "producthunt",
            "sourceUrl": "https://www.producthunt.com/posts/demo",
            "officialUrl": "https://demo.example",
        }
        with (
            patch(
                "api.management.commands.discover_product_hunt."
                "fetch_product_hunt_candidates",
                return_value=[candidate],
            ),
            patch(
                "api.management.commands.discover_product_hunt.dedupe_candidates",
                side_effect=lambda items: items,
            ),
            patch(
                "api.management.commands.discover_product_hunt."
                "run_new_tool_discovery",
                return_value={},
            ) as run,
        ):
            call_command("discover_product_hunt", "--auto-publish")

        assert "producthunt" in settings.EXTERNAL_DISCOVERY_AUTO_PUBLISH_SOURCES
        run.assert_called_once_with(max_new=40, candidates=[candidate])


class TestGitHubDiscoveryExpansion:
    def test_seed_list_includes_reticle(self):
        from api.discovery.sources import GITHUB_SEED_REPOS

        assert "reticlehq/reticle" in GITHUB_SEED_REPOS

    def test_star_queries_target_user_facing_tools(self):
        from api.discovery.github_queries import GITHUB_STAR_QUERIES, MIN_OSS_STARS

        blob = " ".join(GITHUB_STAR_QUERIES).lower()
        assert f"stars:>={MIN_OSS_STARS}" in blob
        assert "fork:false" in blob
        assert "llm-tools" in blob or "mcp-server" in blob or "ai-agents" in blob
        assert "reticle" in blob

    def test_star_bin_splitter_bisects_and_peels_open_ended(self):
        from api.discovery.github_queries import split_star_bin, star_clause

        assert split_star_bin(100, 199) == [(100, 149), (150, 199)]
        assert split_star_bin(10000, None) == [(10000, 19999), (20000, None)]
        assert star_clause(100, 119) == "stars:100..119"
        assert star_clause(10000, None) == "stars:>=10000"

    def test_hn_attribution_credits_discussion(self):
        from api.discovery.facts import Facts
        from api.discovery.generate import hn_attribution_description

        text = hn_attribution_description(
            "WidgetAI",
            Facts(meta_description="Show HN: WidgetAI – AI helper for founders"),
            product_url="https://widget.ai",
            hn_url="https://news.ycombinator.com/item?id=1",
            points=42,
            story_title="Show HN: WidgetAI – AI helper for founders",
        )
        assert "WidgetAI" in text
        assert "Hacker News" in text
        assert "news.ycombinator.com" in text
        assert len(text.split()) >= 30

    def test_oss_attribution_credits_maintainers(self):
        from api.discovery.facts import Facts
        from api.discovery.generate import oss_attribution_description

        text = oss_attribution_description(
            "github/ollama/ollama",
            Facts(
                meta_description="Run large language models locally",
                stars=180000,
                category="llm",
                pricing="free",
            ),
            source_url="https://github.com/ollama/ollama",
            source_type="github",
        )
        assert "ollama" in text.lower()
        assert "GitHub" in text
        assert "credit" in text.lower() or "One9Founders" in text

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
            "stargazers_count": 150,
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
            if "stars:>=" in query or "stars:" in query or "topic:mcp" in query:
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
        assert any("stars:>=" in q or "stars:" in q for q in queries)
        assert any("pushed:>" in q for q in queries)
        assert any("created:>" in q for q in queries)
        assert any("fork:false" in q for q in queries)

    def test_github_search_all_splits_when_total_hits_cap(self, settings):
        from api.discovery.sources import _github_search_all

        settings.GITHUB_TOKEN = "gh-test"
        calls: list[str] = []

        def fake_page(query, *, headers, page=1, per_page=100):
            calls.append(query)
            if "stars:100..199" in query and page == 1:
                return [], 1500
            if "stars:100..149" in query:
                return (
                    [
                        {
                            "html_url": "https://github.com/acme/a",
                            "full_name": "acme/a",
                            "stargazers_count": 120,
                            "fork": False,
                            "archived": False,
                        }
                    ],
                    10,
                )
            if "stars:150..199" in query:
                return (
                    [
                        {
                            "html_url": "https://github.com/acme/b",
                            "full_name": "acme/b",
                            "stargazers_count": 180,
                            "fork": False,
                            "archived": False,
                        }
                    ],
                    10,
                )
            return [], 0

        with patch("api.discovery.sources._github_search_page", side_effect=fake_page):
            items = _github_search_all(
                "topic:llm fork:false archived:false",
                100,
                199,
                headers={"Authorization": "Bearer x"},
            )

        urls = {i["html_url"] for i in items}
        assert urls == {
            "https://github.com/acme/a",
            "https://github.com/acme/b",
        }
        assert any("stars:100..149" in q for q in calls)
        assert any("stars:150..199" in q for q in calls)


class TestHackerNewsDiscovery:
    def test_product_name_strips_show_hn_prefix(self):
        from api.discovery.sources import _hn_product_name

        assert _hn_product_name("Show HN: Cursor – AI code editor") == "Cursor"
        assert _hn_product_name("Ask HN: What AI tools do you use?") == ""
        assert _hn_product_name("Who is hiring?") == ""

    def test_skips_news_and_social_hosts(self):
        from api.discovery.sources import _hn_candidate_from_fields

        assert (
            _hn_candidate_from_fields(
                title="Show HN: Demo AI Writer",
                url="https://www.youtube.com/watch?v=abc",
                points=50,
                object_id="1",
            )
            is None
        )
        assert (
            _hn_candidate_from_fields(
                title="Show HN: Demo AI Writer",
                url="https://news.ycombinator.com/item?id=1",
                points=50,
                object_id="1",
            )
            is None
        )

    def test_requires_ai_signal_and_maps_candidate(self):
        from api.discovery.sources import _hn_candidate_from_fields

        assert (
            _hn_candidate_from_fields(
                title="Show HN: Calendar Sync",
                url="https://calendarsync.example",
                points=20,
                object_id="99",
            )
            is None
        )
        candidate = _hn_candidate_from_fields(
            title="Show HN: DemoLLM – local inference",
            url="https://demollm.example/app",
            points=42,
            object_id="123",
            feed="showstories",
        )
        assert candidate is not None
        assert candidate["name"] == "DemoLLM"
        assert candidate["sourceType"] == "hackernews"
        assert candidate["url"] == "https://demollm.example/app"
        assert candidate["sourceUrl"] == ("https://news.ycombinator.com/item?id=123")
        assert candidate["rawSignal"]["points"] == 42
        assert "Hacker News" in candidate["rawSignal"]["attribution"]

    def test_firebase_feed_maps_ai_stories(self):
        from api.discovery.sources import fetch_hacker_news_firebase_candidates

        item = {
            "id": 42,
            "type": "story",
            "title": "Show HN: AgentPad – AI agent IDE",
            "url": "https://agentpad.example",
            "score": 88,
            "time": 1720000000,
        }
        with (
            patch(
                "api.discovery.sources._hn_firebase_get",
                side_effect=lambda path: (
                    [42, 99] if path == "showstories.json" else item
                ),
            ),
            patch(
                "api.discovery.sources._hn_firebase_item",
                side_effect=lambda item_id: item if item_id == 42 else None,
            ),
            patch("api.discovery.sources.time.sleep"),
        ):
            rows = fetch_hacker_news_firebase_candidates(feeds=("showstories",))

        assert len(rows) == 1
        assert rows[0]["name"] == "AgentPad"
        assert rows[0]["rawSignal"]["feed"] == "showstories"

    def test_algolia_full_sweep_paginates(self):
        from api.discovery.sources import fetch_hacker_news_algolia_candidates

        page0 = [
            {
                "objectID": "1",
                "title": "Show HN: PageOne AI",
                "url": "https://pageone.example",
                "points": 30,
                "created_at": "2024-01-01T00:00:00.000Z",
            }
        ]
        page1 = [
            {
                "objectID": "2",
                "title": "Show HN: PageTwo LLM",
                "url": "https://pagetwo.example",
                "points": 20,
                "created_at": "2024-02-01T00:00:00.000Z",
            }
        ]

        def fake_search(
            query, *, tags, since=None, page=0, hits_per_page=100, by_date=False
        ):
            if page == 0:
                return page0, 2
            if page == 1:
                return page1, 2
            return [], 2

        with (
            patch(
                "api.discovery.sources._hn_algolia_search",
                side_effect=fake_search,
            ),
            patch(
                "api.discovery.sources.HN_FULL_SWEEP_QUERIES",
                (("AI", "show_hn"),),
            ),
            patch("api.discovery.sources.time.sleep"),
        ):
            rows = fetch_hacker_news_algolia_candidates(full_sweep=True)

        urls = {r["url"] for r in rows}
        assert urls == {
            "https://pageone.example",
            "https://pagetwo.example",
        }

    @pytest.mark.django_db
    def test_partition_cross_checks_existing_tools(self):
        from api.discovery.sources import partition_against_catalog

        ToolFactory(name="Cursor", website="https://www.cursor.com/")
        scraped = [
            {
                "name": "Cursor",
                "url": "https://cursor.com",
                "sourceType": "hackernews",
                "rawSignal": {"points": 100},
            },
            {
                "name": "Brand New HN Tool",
                "url": "https://brand-new-hn.example",
                "sourceType": "hackernews",
                "rawSignal": {"points": 10},
            },
        ]
        already, fresh = partition_against_catalog(scraped)
        assert len(already) == 1
        assert already[0]["name"] == "Cursor"
        assert len(fresh) == 1
        assert fresh[0]["name"] == "Brand New HN Tool"

    def test_partition_does_not_collapse_hn_item_query_strings(self):
        """HN sourceUrl is item?id=N; normalize_url strips ?id=, so identity
        must use the official product URL or every story collapses to one."""
        from api.discovery.sources import partition_against_catalog

        scraped = [
            {
                "name": "Tool Alpha AI",
                "url": "https://alpha.example",
                "officialUrl": "https://alpha.example",
                "sourceUrl": "https://news.ycombinator.com/item?id=111",
                "sourceType": "hackernews",
                "rawSignal": {"points": 50},
            },
            {
                "name": "Tool Beta LLM",
                "url": "https://beta.example",
                "officialUrl": "https://beta.example",
                "sourceUrl": "https://news.ycombinator.com/item?id=222",
                "sourceType": "hackernews",
                "rawSignal": {"points": 40},
            },
            {
                "name": "Tool Gamma Agent",
                "url": "https://gamma.example",
                "officialUrl": "https://gamma.example",
                "sourceUrl": "https://news.ycombinator.com/item?id=333",
                "sourceType": "hackernews",
                "rawSignal": {"points": 30},
            },
        ]
        with patch(
            "api.discovery.sources._existing_tools_for_candidates",
            return_value=[],
        ):
            already, fresh = partition_against_catalog(scraped)
        assert already == []
        assert {row["name"] for row in fresh} == {
            "Tool Alpha AI",
            "Tool Beta LLM",
            "Tool Gamma Agent",
        }

    @pytest.mark.django_db
    def test_hn_catalog_dry_run_reports_cross_check_without_writes(self):
        ToolFactory(name="Known", website="https://known.example")
        scraped = [
            {
                "name": "Known",
                "url": "https://known.example",
                "sourceType": "hackernews",
                "rawSignal": {"points": 5},
            },
            {
                "name": "Fresh AI Kit",
                "url": "https://fresh-ai-kit.example",
                "sourceType": "hackernews",
                "rawSignal": {"points": 9},
            },
        ]
        output = StringIO()
        with (
            patch(
                "api.management.commands.discover_hn_catalog."
                "fetch_hacker_news_candidates",
                return_value=scraped,
            ),
            patch(
                "api.management.commands.discover_hn_catalog." "run_new_tool_discovery",
            ) as run,
        ):
            call_command("discover_hn_catalog", "--dry-run", stdout=output)

        text = output.getvalue()
        assert "scraped: 2" in text
        assert "already_on_site: 1" in text
        assert "new_candidates: 1" in text
        assert "[on-site] Known" in text
        assert "[new] Fresh AI Kit" in text
        run.assert_not_called()


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
