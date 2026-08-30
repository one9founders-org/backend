from unittest.mock import MagicMock

import pytest

from api.fintech import seed_kyc_preview
from api.fintech_catalog import CatalogVendor
from api.fintech_ingest import coerce_scores, ingest_vendor, run
from api.firecrawl import MappedLink, ScrapedPage
from api.models import FintechEvidencePage, FintechRating, Tool

HOMEPAGE = "https://surepass.io/"

PRIVACY_MD = (
    "Surepass stores and processes customer KYC data in India. "
    "Users may withdraw consent through the DPDP consent manager. "
    "ISO 27001 and SOC 2 Type II certified. "
    "Series B funding from Indian investors. "
    "Models return reason codes for every KYC decision. "
    "We published a 2024 disparate-impact bias audit of the liveness model."
)


def _vendor(**kwargs):
    defaults = dict(
        slug="surepass",
        name="Surepass",
        website=HOMEPAGE,
        stack="kyc",
        one_liner="Digital KYC APIs.",
        india_relevance="India onboarding APIs.",
        hand_reviewed=False,
    )
    defaults.update(kwargs)
    return CatalogVendor(**defaults)


@pytest.mark.django_db
class TestIngestVendor:
    def test_skips_hand_reviewed_preview(self):
        vendor = _vendor(slug="signzy", name="Signzy", hand_reviewed=True)
        before = FintechRating.objects.filter(tool__slug="signzy").count()
        outcome = ingest_vendor(vendor, fetch=True, apply=True)
        assert outcome.skipped == "hand_reviewed"
        assert FintechRating.objects.filter(tool__slug="signzy").count() == before

    def test_plan_only_does_not_call_firecrawl_or_write(self):
        client = MagicMock()
        before = FintechRating.objects.count()
        outcome = ingest_vendor(_vendor(), client=client, fetch=False, apply=False)
        assert outcome.skipped == "plan_only"
        client.map.assert_not_called()
        assert FintechRating.objects.count() == before

    def test_fetch_apply_writes_cited_ratings(self):
        page = ScrapedPage(url=HOMEPAGE, title="Surepass", markdown=PRIVACY_MD)
        client = MagicMock()
        client.map.return_value = [MappedLink(url=HOMEPAGE, title="Home")]
        client.scrape.return_value = page

        def score_fn(vendor, pages):
            return {
                "short_description": vendor.one_liner,
                "india_relevance": vendor.india_relevance,
                "checks": coerce_scores(
                    [
                        {
                            "id": "dataLocalization",
                            "result": "pass",
                            "rationale": "Homepage states India processing.",
                            "evidence_url": HOMEPAGE,
                            "evidence_label": "Home",
                            "quote": "stores and processes customer KYC data in India",
                        }
                    ],
                    {p.url: p.markdown for p in pages},
                ),
            }

        outcome = ingest_vendor(
            _vendor(),
            client=client,
            score_fn=score_fn,
            fetch=True,
            apply=True,
        )
        assert outcome.wrote is True
        assert outcome.results["dataLocalization"] == "pass"
        tool = Tool.objects.get(slug="surepass")
        assert tool.overall_score is None
        assert tool.assessment_detail in ({}, None)
        assert FintechEvidencePage.objects.filter(tool=tool).count() == 1
        row = FintechRating.objects.get(tool=tool, criterion__slug="dataLocalization")
        assert row.result == "pass"
        assert row.evidence_url == HOMEPAGE
        unknown = FintechRating.objects.get(tool=tool, criterion__slug="biasTesting")
        assert unknown.result == "unknown"
        assert unknown.evidence_url == ""

    def test_does_not_overwrite_existing_kyc_preview_without_refresh(self):
        seed_kyc_preview()
        vendor = _vendor(
            slug="signzy",
            name="Signzy",
            website="https://www.signzy.com/",
            hand_reviewed=False,
        )
        outcome = ingest_vendor(vendor, fetch=True, apply=True, refresh=False)
        assert outcome.skipped == "already_rated"
        assert FintechRating.objects.filter(tool__slug="signzy").count() == 6


@pytest.mark.django_db
class TestIngestRun:
    def test_limit_and_skip_reviewed_in_plan(self):
        summary = run(stack="kyc", limit=5, fetch=False, apply=False)
        assert summary["count"] == 5
        skipped = [
            row.slug for row in summary["outcomes"] if row.skipped == "hand_reviewed"
        ]
        assert "signzy" in skipped
        planned = [row for row in summary["outcomes"] if row.skipped == "plan_only"]
        assert planned
        assert summary["estimated_credits"] == len(planned) * 9
