from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.hygiene.classify import FLAG_SENTENCE_NAME, GPT_STORE, NO_URL, PRODUCT
from api.hygiene.visibility import publishable_queryset, row_is_publishable
from api.tool_stats import TOOL_STATS_CACHE_KEY
from tests.factories import CategoryFactory, ToolFactory


@pytest.fixture
def api_client():
    return APIClient()


def _product(**kwargs):
    kwargs.setdefault("website", "https://example.com")
    kwargs.setdefault("entry_type", PRODUCT)
    return ToolFactory(**kwargs)


def _gpt(**kwargs):
    kwargs.setdefault("name", "Expert Economist")
    kwargs.setdefault("website", "https://chat.openai.com/g/g-abc")
    kwargs.setdefault("entry_type", GPT_STORE)
    return ToolFactory(**kwargs)


@pytest.mark.django_db
class TestPublishableQueryset:
    def test_hides_gpt_store_no_url_sentence_names_and_dead_links(self):
        keep = _product(name="Figma", website="https://figma.com")
        _gpt()
        _product(name="Orphan", website="", entry_type=NO_URL)
        _product(
            name="Prompt Posing As A Product For Anything",
            hygiene_flags=[FLAG_SENTENCE_NAME],
        )
        _product(name="DeadSite", website="https://aidiary.io", link_status="broken")
        _product(name="Parked", website="https://useclarity.com", link_status="parked")
        # Unchecked products stay visible until the hygiene pass runs.
        pending = _product(name="NewArrival", link_status="unchecked")

        names = set(publishable_queryset().values_list("name", flat=True))
        assert names == {keep.name, pending.name}
        assert row_is_publishable(keep) is True
        assert row_is_publishable(pending) is True


@pytest.mark.django_db
class TestDirectoryHidesNonProducts:
    def setup_method(self):
        cache.clear()

    def test_list_omits_gpt_store_rows(self, api_client):
        visible = _product(name="Figma", website="https://figma.com")
        hidden = _gpt()

        response = api_client.get(reverse("tool-list"))

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data["results"]]
        assert visible.name in names
        assert hidden.name not in names

    def test_list_exposes_entry_type_and_popularity_score(self, api_client):
        _product(name="Notion AI", popularity_score="0.4200")

        response = api_client.get(reverse("tool-list"))
        row = response.data["results"][0]

        assert row["entry_type"] == PRODUCT
        assert float(row["popularity_score"]) == pytest.approx(0.42)

    def test_retrieve_gpt_store_row_is_not_found(self, api_client):
        hidden = _gpt(name="The Laughing Parrot")

        response = api_client.get(reverse("tool-detail", kwargs={"slug": hidden.slug}))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_product_still_works(self, api_client):
        tool = _product(name="Linear")

        response = api_client.get(reverse("tool-detail", kwargs={"slug": tool.slug}))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["entry_type"] == PRODUCT
        assert "popularity_score" in response.data

    @patch("api.faiss_search.FAISSSearchService.get_instance")
    def test_search_omits_gpt_store_rows(self, mock_faiss, api_client):
        mock_instance = MagicMock()
        mock_instance.search.return_value = None
        mock_faiss.return_value = mock_instance
        _product(name="WriterAI", description="writes copy")
        _gpt(name="Expert Writer", description="writes copy")

        response = api_client.post(
            reverse("tool-search"), {"query": "writes"}, format="json"
        )

        names = [row["name"] for row in response.data]
        assert "WriterAI" in names
        assert "Expert Writer" not in names

    def test_trending_omits_gpt_store_rows(self, api_client):
        _product(name="VisibleTrend")
        _gpt(name="HiddenTrend")

        response = api_client.get(reverse("trending-tools"))

        names = [row["name"] for row in response.data]
        assert "VisibleTrend" in names
        assert "HiddenTrend" not in names

    def test_stats_and_category_counts_ignore_gpt_rows(self, api_client):
        writing = CategoryFactory(name="Writing", slug="writing-hygiene")
        _product(name="RealWriter", categories=[writing], criteria_completed=10)
        _gpt(name="FakeWriter", categories=[writing])

        stats = api_client.get(reverse("tool-directory-stats"))
        assert stats.data["count"] == 1
        assert stats.data["total_tools"] == 2
        assert stats.data["by_category"] == [{"category": "Writing", "count": 1}]

        categories = api_client.get(reverse("category-list"))
        writing_row = next(
            row
            for row in categories.data["results"]
            if row["slug"] == "writing-hygiene"
        )
        assert writing_row["tool_count"] == 1
        cache.delete(TOOL_STATS_CACHE_KEY)
