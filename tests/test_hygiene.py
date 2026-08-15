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
from api.hygiene.linkcheck import is_malformed
from api.hygiene.rank import RankInputs, completeness_score, display_order_for
from api.hygiene.rank import score as rank_score
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
