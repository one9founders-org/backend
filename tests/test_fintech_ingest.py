from unittest.mock import MagicMock

import pytest

from api.fintech_catalog import vendors_for
from api.fintech_ingest import coerce_scores, pick_urls, quote_supported
from api.firecrawl import FirecrawlClient, MappedLink


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests():
    """Override the project-wide fixture: this module is pure logic, no DB."""


HOMEPAGE = "https://surepass.io/"

PRIVACY_MD = (
    "Surepass stores and processes customer KYC data in India. "
    "Users may withdraw consent through the DPDP consent manager. "
    "ISO 27001 and SOC 2 Type II certified. "
    "Series B funding from Indian investors. "
    "Models return reason codes for every KYC decision. "
    "We published a 2024 disparate-impact bias audit of the liveness model."
)


class TestPickUrls:
    def test_homepage_first_then_privacy_over_careers(self):
        mapped = [
            MappedLink(url="https://surepass.io/careers", title="Jobs"),
            MappedLink(url="https://surepass.io/privacy-policy", title="Privacy"),
            MappedLink(url="https://surepass.io/blog/hello", title="Blog"),
            MappedLink(url="https://unrelated.com/security", title="Security"),
        ]
        urls = pick_urls(HOMEPAGE, mapped, max_pages=3)
        assert urls[0] == HOMEPAGE
        assert "https://surepass.io/privacy-policy" in urls
        assert "https://surepass.io/careers" not in urls
        assert "https://unrelated.com/security" not in urls


class TestQuoteSupport:
    def test_whitespace_and_case_are_ignored(self):
        assert quote_supported(
            "stores and  PROCESSES customer KYC data in India",
            PRIVACY_MD,
        )

    def test_short_or_missing_quote_fails(self):
        assert not quote_supported("India", PRIVACY_MD)
        assert not quote_supported(
            "this sentence is not on the page at all", PRIVACY_MD
        )


class TestCoerceScores:
    def test_pass_without_quote_becomes_unknown(self):
        pages = {HOMEPAGE: PRIVACY_MD}
        raw = [
            {
                "id": "dataLocalization",
                "result": "pass",
                "rationale": "They store data in India.",
                "evidence_url": HOMEPAGE,
                "evidence_label": "Home",
                "quote": "not actually on the page",
            }
        ]
        scored = {row["check"]: row for row in coerce_scores(raw, pages)}
        assert scored["dataLocalization"]["result"] == "unknown"
        assert scored["dataLocalization"]["evidence_url"] == ""
        assert scored["biasTesting"]["result"] == "unknown"

    def test_pass_with_verbatim_quote_keeps_url(self):
        pages = {HOMEPAGE: PRIVACY_MD}
        raw = [
            {
                "id": "dataLocalization",
                "result": "pass",
                "rationale": "Homepage states India processing.",
                "evidence_url": HOMEPAGE,
                "evidence_label": "Home",
                "quote": "stores and processes customer KYC data in India",
            }
        ]
        scored = {row["check"]: row for row in coerce_scores(raw, pages)}
        assert scored["dataLocalization"]["result"] == "pass"
        assert scored["dataLocalization"]["evidence_url"] == HOMEPAGE


class TestCatalog:
    def test_catalog_has_all_three_stacks(self):
        slugs = {row.stack for row in vendors_for()}
        assert slugs == {"kyc", "credit", "fraud"}
        assert len(vendors_for()) >= 30


class TestFirecrawlClientParse:
    def test_map_accepts_string_or_object_links(self, settings):
        settings.FIRECRAWL_API_KEY = "fc-test"
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "success": True,
            "links": [
                "https://surepass.io/privacy",
                {"url": "https://surepass.io/security", "title": "Security"},
            ],
        }
        session.post.return_value = response
        client = FirecrawlClient(session=session, min_interval=0)
        links = client.map(HOMEPAGE)
        assert [link.url for link in links] == [
            "https://surepass.io/privacy",
            "https://surepass.io/security",
        ]
        assert links[1].title == "Security"

    def test_retries_429_then_succeeds(self, settings, monkeypatch):
        settings.FIRECRAWL_API_KEY = "fc-test"
        monkeypatch.setattr("api.firecrawl.time.sleep", lambda *_: None)
        limited = MagicMock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "1"}
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = {
            "success": True,
            "data": {"markdown": "ok", "metadata": {"title": "Home"}},
        }
        session = MagicMock()
        session.post.side_effect = [limited, ok]
        client = FirecrawlClient(session=session, min_interval=0)
        page = client.scrape(HOMEPAGE)
        assert page.markdown == "ok"
        assert session.post.call_count == 2
