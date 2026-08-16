import sqlite3

import pytest

from api.hygiene.classify import (
    APP_LISTING,
    ENTRY_TYPE_CHOICES,
    EXTENSION,
    GPT_STORE,
    NO_URL,
    PRODUCT,
    UNPUBLISHABLE_ENTRY_TYPES,
    classify,
    entry_type_for,
    host_of,
    is_publishable,
    name_flags,
    normalized_name,
)
from api.hygiene.linkcheck import PARKED_CODES, is_malformed
from api.hygiene.pipeline import Stages
from api.hygiene.rank import RankInputs, completeness_score, display_order_for
from api.hygiene.rank import score as rank_score
from api.hygiene.signals import (
    Signals,
    external_score,
    fetch_wikidata,
    hn_score,
    is_shared_host,
    lookup_tranco,
)
from api.hygiene.signals import rank_score as tranco_rank_score
from api.hygiene.taxonomy import (
    VOCABULARY,
    balance,
    dedupe,
    facet_of,
    infer_tags,
    migrate_legacy_tags,
)
from api.hygiene.websearch import SearchEvidence, search_footprint_score


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests():
    """Override the project-wide fixture: this module is pure logic, no DB."""


class TestClassify:
    def test_host_of_strips_www_and_port(self):
        assert host_of("https://www.Example.com:8000/path") == "example.com"
        assert host_of("example.com/x") == "example.com"
        assert host_of("") == ""

    def test_gpt_store_rows_are_not_products(self):
        assert entry_type_for("https://chat.openai.com/g/g-abc") == GPT_STORE
        assert entry_type_for("https://chatgpt.com/g/g-abc") == GPT_STORE

    def test_platform_listings_are_detected(self):
        assert entry_type_for("https://apps.apple.com/us/app/x/id1") == APP_LISTING
        assert entry_type_for("https://chromewebstore.google.com/detail/x") == EXTENSION
        assert entry_type_for("https://acme.com") == PRODUCT
        assert entry_type_for("") == NO_URL

    def test_name_flags_catch_real_production_junk(self):
        assert "name_leading_punctuation" in name_flags("!Expert")
        assert "name_has_version_suffix" in name_flags("Mumble Note: Notetakerv0.7.16")
        assert "name_truncated" in name_flags("Resemble AI - Voice Conver...")
        assert "name_is_a_sentence" in name_flags(
            "Expert in top 10 actions for success in any topic"
        )

    def test_clean_names_raise_no_flags(self):
        assert name_flags("Notion AI") == []
        assert name_flags("Figma") == []

    def test_publishability_excludes_gpt_and_prompt_names(self):
        assert is_publishable(*classify("Figma", "https://figma.com")) is True
        assert (
            is_publishable(*classify("Expert Economist", "https://chat.openai.com/g/x"))
            is False
        )
        assert is_publishable(PRODUCT, ["name_is_a_sentence"]) is False

    def test_unpublishable_entry_types_match_the_predicate(self):
        for key, _label in ENTRY_TYPE_CHOICES:
            expected = key not in UNPUBLISHABLE_ENTRY_TYPES
            assert is_publishable(key, []) is expected

    def test_normalized_name_collapses_punctuation(self):
        assert normalized_name("Notion-AI!") == normalized_name("notion ai")


class TestLinkChecks:
    def test_store_urls_without_an_id_are_malformed(self):
        assert is_malformed("https://play.google.com/store/apps/details")
        assert not is_malformed("https://play.google.com/store/apps/details?id=com.x")

    def test_structurally_broken_urls_are_caught(self):
        assert is_malformed("")
        assert is_malformed("not a url")

    def test_normal_urls_pass(self):
        assert is_malformed("https://figma.com") == ""

    def test_bot_walls_are_not_treated_as_parked(self):
        assert 403 not in PARKED_CODES
        assert 402 in PARKED_CODES
        assert 410 in PARKED_CODES


class TestTaxonomy:
    def test_every_tag_has_a_known_facet(self):
        for tag in VOCABULARY:
            assert facet_of(tag) is not None

    def test_legacy_tags_map_onto_the_new_vocabulary(self):
        assert migrate_legacy_tags(["Assistant"]) == ["Chat Assistant"]
        assert "Content Writing" in migrate_legacy_tags(["Copywriting"])
        assert migrate_legacy_tags(["nonsense-tag"]) == []

    def test_inference_finds_tags_from_free_text(self):
        tags = infer_tags("An AI chatbot that helps founders automate their workflow")
        assert "Chat Assistant" in tags
        assert "Automation" in tags

    def test_dedupe_drops_unknown_tags(self):
        assert dedupe(["Marketing", "Marketing", "Bogus"]) == ["Marketing"]

    def test_balance_caps_a_single_facet(self):
        function_tags = [t for t, (f, _) in VOCABULARY.items() if f == "function"][:6]
        assert len(balance(function_tags, max_per_facet=3)) == 3


class TestRanking:
    def test_completeness_rewards_populated_records(self):
        empty = completeness_score({})
        full = completeness_score(
            {
                "short_description": "x",
                "description": "y",
                "logo_url": "z",
                "website": "w",
                "tags": ["Marketing"],
                "use_cases": ["a"],
                "pricing_type": "free",
                "features": ["f"],
            }
        )
        assert empty == 0.0
        assert full == 1.0

    def test_broken_links_are_heavily_penalised(self):
        healthy = RankInputs(external_score=0.8, clicks=50, completeness=1.0)
        broken = RankInputs(
            external_score=0.8, clicks=50, completeness=1.0, penalties=["broken_link"]
        )
        assert rank_score(broken) < rank_score(healthy) * 0.5

    def test_score_stays_within_bounds(self):
        assert rank_score(RankInputs()) == 0.0
        maxed = rank_score(
            RankInputs(
                external_score=1.0, clicks=10_000, views=10_000, completeness=1.0
            )
        )
        assert 0.0 <= maxed <= 1.0

    def test_display_order_inverts_score(self):
        assert display_order_for(1.0) < display_order_for(0.0)


class TestFreeSignals:
    @staticmethod
    def _db():
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE ranks (domain TEXT PRIMARY KEY, rank INTEGER)")
        connection.executemany(
            "INSERT INTO ranks VALUES (?, ?)",
            [("github.io", 117), ("t.me", 108), ("figma.com", 400), ("acme.com", 5000)],
        )
        return connection

    def test_exact_domain_rank_is_used(self):
        rank, inherited = lookup_tranco("figma.com", self._db())
        assert (rank, inherited) == (400, False)

    def test_shared_hosting_never_inherits_the_platform_rank(self):
        """A GitHub Pages demo must not inherit github.io's global rank."""
        rank, inherited = lookup_tranco("someuser.github.io", self._db())
        assert rank is None
        assert inherited is False

        rank, _ = lookup_tranco("zoefit_bot.t.me", self._db())
        assert rank is None

    def test_ordinary_subdomains_still_inherit_but_are_marked(self):
        rank, inherited = lookup_tranco("app.acme.com", self._db())
        assert rank == 5000
        assert inherited is True

    def test_inherited_ranks_score_lower_than_direct_ones(self):
        assert tranco_rank_score(400, inherited=True) < tranco_rank_score(400)
        assert tranco_rank_score(None) == 0.0

    def test_better_ranks_score_higher(self):
        assert tranco_rank_score(500) > tranco_rank_score(80_000)
        assert tranco_rank_score(80_000) > tranco_rank_score(900_000)

    def test_is_shared_host_matches_platform_subdomains(self):
        assert is_shared_host("foo.vercel.app")
        assert is_shared_host("github.io")
        assert not is_shared_host("figma.com")

    def test_hn_score_needs_stories(self):
        assert hn_score(0, 0) == 0.0
        assert hn_score(5, 900) > hn_score(1, 20)

    def test_external_score_penalises_shared_hosting(self):
        hosted = Signals(tranco_rank=5_000, shared_hosting=True)
        owned = Signals(tranco_rank=5_000)
        assert external_score(hosted) < external_score(owned)

    def test_wikidata_requires_a_website_to_disambiguate(self):
        """Without a site to match P856 against, "Perplexity" resolves to a
        1990 video game. Refuse to guess rather than return a wrong entity."""
        assert fetch_wikidata("Perplexity", "") == ("", "")
        assert fetch_wikidata("", "https://perplexity.ai") == ("", "")

    def test_external_score_is_bounded(self):
        assert external_score(Signals()) == 0.0
        best = external_score(
            Signals(
                tranco_rank=50,
                wikidata_id="Q123",
                hn_story_count=20,
                hn_points=5000,
            )
        )
        assert 0.0 < best <= 1.0

    def test_paid_search_is_off_unless_opted_in(self):
        stages = Stages()
        assert stages.signals is True
        assert stages.search is False
        assert stages.llm is True


class TestSearchEvidence:
    def test_unresolved_search_scores_zero(self):
        assert search_footprint_score(SearchEvidence(ok=False)) == 0.0

    def test_official_site_and_directories_raise_the_score(self):
        weak = SearchEvidence(ok=True, total_results=500)
        strong = SearchEvidence(
            ok=True,
            total_results=2_000_000,
            official_site_matched=True,
            directory_hits=["g2.com", "producthunt.com", "capterra.com", "github.com"],
        )
        assert search_footprint_score(strong) > search_footprint_score(weak)
        assert search_footprint_score(strong) <= 1.0


class TestTrack:
    def test_github_repo_is_open_source(self):
        from api.hygiene.track import OPEN_SOURCE, classify_track

        assert (
            classify_track("LangChain", "https://github.com/langchain-ai/langchain")
            == OPEN_SOURCE
        )

    def test_mcp_name_wins_over_github(self):
        from api.hygiene.track import MCP_SERVER, classify_track

        assert (
            classify_track("Filesystem MCP", "https://github.com/acme/filesystem-mcp")
            == MCP_SERVER
        )

    def test_skill_pack_is_not_an_agent(self):
        from api.hygiene.track import AGENT_SKILL, classify_track

        assert (
            classify_track(
                "Marketing skills",
                "https://github.com/acme/marketing-skills",
                "Marketing skills for Claude Code and AI agents",
            )
            == AGENT_SKILL
        )

    def test_hosted_saas_is_an_ai_tool(self):
        from api.hygiene.track import AI_TOOL, classify_track

        assert classify_track("Notion", "https://notion.so") == AI_TOOL

    def test_agent_platform_phrase(self):
        from api.hygiene.track import AI_AGENT, classify_track

        assert (
            classify_track(
                "Devin",
                "https://devin.ai",
                "An autonomous agent that writes pull requests",
            )
            == AI_AGENT
        )


class TestAssessScoring:
    def test_score_without_citation_is_dropped(self):
        from api.hygiene.assess import _valid_entry

        index = {
            "https://acme.com/privacy": {
                "url": "https://acme.com/privacy",
                "present": True,
            }
        }
        assert _valid_entry({"score": 8, "evidence_url": ""}, index) is None
        assert (
            _valid_entry(
                {"score": 8, "evidence_url": "https://invented.example"}, index
            )
            is None
        )

    def test_cited_url_must_come_from_evidence(self):
        from api.hygiene.assess import _valid_entry

        index = {
            "https://acme.com/privacy": {
                "url": "https://acme.com/privacy",
                "present": True,
                "absence": False,
            }
        }
        entry = _valid_entry(
            {
                "score": 7,
                "evidence_url": "https://acme.com/privacy",
                "reasoning": "Policy found.",
            },
            index,
        )
        assert entry["score"] == 7
        assert entry["evidence_url"] == "https://acme.com/privacy"

    def test_404_cannot_support_a_high_score(self):
        from api.hygiene.assess import _valid_entry

        index = {
            "https://acme.com/privacy": {
                "url": "https://acme.com/privacy",
                "present": False,
                "absence": True,
                "http_status": 404,
            }
        }
        assert (
            _valid_entry(
                {"score": 8, "evidence_url": "https://acme.com/privacy"}, index
            )
            is None
        )
        low = _valid_entry(
            {
                "score": 2,
                "evidence_url": "https://acme.com/privacy",
                "reasoning": "No policy.",
            },
            index,
        )
        assert low["score"] == 2

    def test_overall_stays_null_below_six_criteria(self):
        from api.hygiene.assess import overall_from, security_score_from

        scored = {
            "security_privacy": {"score": 8},
            "functionality": {"score": 6},
            "pricing_value": {"score": 5},
        }
        assert overall_from(scored) is None
        assert security_score_from(scored) == 16

    def test_overall_is_unweighted_mean_on_five_scale(self):
        from api.hygiene.assess import overall_from

        scored = {f"c{i}": {"score": 8} for i in range(6)}
        assert overall_from(scored) == 4.0

    def test_token_cost_matches_published_mini_rates(self):
        from api.hygiene.assess import token_cost_usd

        # 1M in + 1M out at $0.15 / $0.60
        assert token_cost_usd(1_000_000, 1_000_000, "gpt-4o-mini") == pytest.approx(
            0.75
        )

    def test_unknown_model_is_priced_as_gpt4o(self):
        from api.hygiene.assess import token_cost_usd

        assert token_cost_usd(1_000_000, 0, "mystery-model") == pytest.approx(2.50)

    def test_assessment_detail_includes_manual_criteria_as_null(self):
        from api.hygiene.assess import MANUAL_ONLY, assessment_detail

        detail = assessment_detail(
            {
                "scored": {
                    "security_privacy": {
                        "score": 6,
                        "evidence_url": "https://acme.com/privacy",
                        "reasoning": "Policy present.",
                    }
                },
                "unassessed": ["functionality"],
            },
            model="gpt-4o-mini",
        )
        assert detail["hands_on"] is False
        assert detail["method"] == "published_evidence"
        for cid in MANUAL_ONLY:
            assert detail["criteria"][cid]["score"] is None
            assert detail["criteria"][cid]["automated"] is False


class TestEvidenceCollector:
    def test_html_pass_caps_body_fetches_at_six(self, monkeypatch):
        from api.hygiene.evidence import (
            clear_evidence_cache,
            collect_html_evidence,
        )
        from api.hygiene.linkcheck import OK, LinkResult

        clear_evidence_cache()
        calls = []

        def fake_check(_url):
            return LinkResult(status=OK, http_code=200, final_url="https://acme.com/")

        def fake_fetch(url):
            calls.append(url)
            return {
                "url": url,
                "text": "hello",
                "http_status": 200,
                "present": True,
                "https": True,
                "absence": False,
            }

        monkeypatch.setattr("api.hygiene.evidence.check_url", fake_check)
        monkeypatch.setattr("api.hygiene.evidence.fetch_page", fake_fetch)
        evidence = collect_html_evidence("https://acme.com")
        assert len(calls) <= 6
        assert evidence["transport"]["https"] is True
        assert "homepage" in evidence

    def test_negative_results_are_cached(self, monkeypatch):
        from api.hygiene.evidence import clear_evidence_cache, fetch_page

        clear_evidence_cache()
        hits = {"n": 0}

        class FakeResponse:
            status_code = 404
            url = "https://acme.com/security"
            text = "not found"

        def fake_get(*_args, **_kwargs):
            hits["n"] += 1
            return FakeResponse()

        monkeypatch.setattr("api.hygiene.evidence.requests.get", fake_get)
        first = fetch_page("https://acme.com/security")
        second = fetch_page("https://acme.com/security")
        assert hits["n"] == 1
        assert first["absence"] is True
        assert second["present"] is False
        assert "HTTP 404" in first["text"]
