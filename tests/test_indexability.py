"""Tests for sitemap indexability filters."""

import pytest

from api.hygiene.indexability import indexable_queryset
from api.hygiene.visibility import publishable_queryset
from tests.factories import ToolFactory


@pytest.mark.django_db
class TestIndexableSitemapFilter:
    def test_substantive_description_is_indexable(self):
        tool = ToolFactory(
            name="Substantive Tool",
            description=(
                "A substantive product description with enough words for the "
                "sitemap indexability gate so Google is asked to index this "
                "listing rather than a thin stub page without real content."
            ),
            pricing_models=["paid"],
            use_cases=["Coding"],
        )
        assert tool in list(indexable_queryset())

    def test_thin_stub_excluded_even_when_publishable(self):
        tool = ToolFactory(
            name="Thin Stub Tool",
            description="Short.",
            pricing_models=[],
            use_cases=[],
            pricing_type="",
            criteria_completed=0,
            website="",
        )
        assert tool in list(publishable_queryset())
        assert tool not in list(indexable_queryset())

    def test_assessed_tool_included_even_with_short_description(self):
        tool = ToolFactory(
            name="Assessed Short Tool",
            description="Short.",
            criteria_completed=6,
            overall_score=3.5,
            pricing_models=[],
            use_cases=[],
        )
        assert tool in list(indexable_queryset())

    def test_hn_catalogue_with_blurb_and_website(self):
        tool = ToolFactory(
            name="HN Catalogue Tool",
            description="A short but useful Show HN blurb for founders.",
            short_description="Show HN launch",
            tags=["hackernews"],
            website="https://example.com/hn-tool",
            pricing_models=[],
            use_cases=[],
            pricing_type="",
            criteria_completed=0,
        )
        assert tool in list(indexable_queryset())
