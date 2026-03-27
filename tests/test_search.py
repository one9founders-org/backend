from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_tool(db):
    from api.models import Tool

    return Tool.objects.create(
        name="EmailBot Pro",
        short_description="AI tool for writing cold emails",
        description="A powerful AI tool that helps you craft cold emails",
        is_active=True,
        pricing_type="freemium",
    )


@pytest.fixture
def inactive_tool(db):
    from api.models import Tool

    return Tool.objects.create(
        name="DeadTool",
        short_description="This tool is inactive",
        description="Should not appear in search results",
        is_active=False,
    )


@pytest.mark.django_db
class TestBasicSearch:
    def test_empty_query_returns_empty_list(self, api_client):
        response = api_client.post(
            "/api/tools/search/",
            {"query": ""},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @patch("api.faiss_search.FAISSSearchService.get_instance")
    def test_text_fallback_finds_tool_by_name(
        self, mock_faiss, api_client, sample_tool
    ):
        mock_instance = MagicMock()
        mock_instance.search.return_value = None
        mock_faiss.return_value = mock_instance

        response = api_client.post(
            "/api/tools/search/",
            {"query": "EmailBot"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert any(t["name"] == "EmailBot Pro" for t in data)

    @patch("api.faiss_search.FAISSSearchService.get_instance")
    def test_text_fallback_finds_tool_by_description(
        self, mock_faiss, api_client, sample_tool
    ):
        mock_instance = MagicMock()
        mock_instance.search.return_value = None
        mock_faiss.return_value = mock_instance

        response = api_client.post(
            "/api/tools/search/",
            {"query": "cold emails"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert any(t["name"] == "EmailBot Pro" for t in data)

    @patch("api.faiss_search.FAISSSearchService.get_instance")
    def test_inactive_tools_not_returned(
        self, mock_faiss, api_client, sample_tool, inactive_tool
    ):
        mock_instance = MagicMock()
        mock_instance.search.return_value = None
        mock_faiss.return_value = mock_instance

        response = api_client.post(
            "/api/tools/search/",
            {"query": "tool"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        tool_names = [t["name"] for t in data]
        assert "DeadTool" not in tool_names


@pytest.mark.django_db
class TestSmartSearch:
    @patch("api.smart_search_views.smart_search")
    def test_smart_search_returns_200(self, mock_search, api_client):
        mock_search.return_value = [{"id": 1, "name": "TestTool", "similarity": 0.9}]
        response = api_client.post(
            "/api/tools/smart-search/",
            {"query": "email tools"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "TestTool"

    def test_smart_search_returns_400_for_long_query(self, api_client):
        long_query = "x" * 501
        response = api_client.post(
            "/api/tools/smart-search/",
            {"query": long_query},
            format="json",
        )
        assert response.status_code == 400
        assert "too long" in response.json()["error"].lower()

    @patch(
        "api.smart_search_views.smart_search",
        side_effect=Exception("boom"),
    )
    def test_smart_search_graceful_degradation(self, mock_search, api_client):
        response = api_client.post(
            "/api/tools/smart-search/",
            {"query": "email tools"},
            format="json",
        )
        assert response.status_code == 200
        assert response.json() == []


class TestParseIntent:
    @patch("api.smart_search.openai_client")
    def test_parse_intent_fallback_on_openai_error(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("OpenAI down")

        from api.smart_search import parse_intent

        result = parse_intent("best email writing tools")
        assert "primary_intent" in result
        assert result["primary_intent"] == "best email writing tools"
        assert isinstance(result["keywords"], list)
        assert len(result["keywords"]) > 0
