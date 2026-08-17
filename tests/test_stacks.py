from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from tests.factories import ToolFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def catalog(db):
    oss = ToolFactory(
        name="python-seo-analyzer",
        slug="python-seo-analyzer",
        short_description="Crawls and audits site structure",
        description="Open source SEO auditor",
        website="https://github.com/sethblack/python-seo-analyzer",
        pricing_type="free",
        free_tier_available=True,
        tags=["seo", "open-source"],
        is_active=True,
    )
    skill = ToolFactory(
        name="marketingskills",
        slug="marketingskills",
        short_description="Marketing skills for Claude Code",
        description="SKILL.md pack for SEO briefs",
        website="https://github.com/example/marketingskills",
        pricing_type="free",
        free_tier_available=True,
        tags=["skills", "claude"],
        is_active=True,
    )
    hosted = ToolFactory(
        name="SEOmatic AI",
        slug="seomatic-ai",
        short_description="Hosted technical SEO",
        description="A hosted SEO product",
        website="https://seomatic.ai",
        pricing_type="paid",
        pricing_from=29,
        free_tier_available=False,
        tags=["seo"],
        is_active=True,
    )
    return {"oss": oss, "skill": skill, "hosted": hosted}


def _search_rows(catalog):
    return [
        {
            "id": catalog["oss"].id,
            "slug": "python-seo-analyzer",
            "name": catalog["oss"].name,
        },
        {
            "id": catalog["skill"].id,
            "slug": "marketingskills",
            "name": catalog["skill"].name,
        },
        {
            "id": catalog["hosted"].id,
            "slug": "seomatic-ai",
            "name": catalog["hosted"].name,
        },
    ]


@pytest.mark.django_db
class TestAssembleStack:
    def test_empty_query_400(self, api_client):
        response = api_client.post("/stacks/assemble/", {"query": ""}, format="json")
        assert response.status_code == 400

    def test_long_query_400(self, api_client):
        response = api_client.post(
            "/stacks/assemble/", {"query": "x" * 501}, format="json"
        )
        assert response.status_code == 400

    @patch("api.stack_assemble._llm_picks", return_value=None)
    @patch("api.stack_assemble.smart_search")
    def test_heuristic_saves_and_returns_id(
        self, mock_search, _mock_llm, api_client, catalog
    ):
        mock_search.return_value = _search_rows(catalog)
        response = api_client.post(
            "/stacks/assemble/",
            {"query": "I want to start SEO marketing for my SaaS"},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["public_id"]
        assert data["source"] == "agent"
        assert data["url_path"] == f"/stack/{data['public_id']}"
        lane_ids = [lane["id"] for lane in data["lanes"]]
        assert "worker" in lane_ids
        slugs = [item.get("slug") for lane in data["lanes"] for item in lane["items"]]
        assert "python-seo-analyzer" in slugs
        assert None in slugs  # Worker

        stored = api_client.get(f"/stacks/{data['public_id']}/")
        assert stored.status_code == 200
        assert stored.json()["query"].startswith("I want to start SEO")

    @patch("api.stack_assemble.smart_search")
    def test_llm_cannot_invent_tools(self, mock_search, api_client, catalog):
        mock_search.return_value = _search_rows(catalog)
        fake = {
            "title": "SEO stack",
            "blurb": "Start SEO without a retainer.",
            "cash_out": "Free first.",
            "picks": [
                {
                    "slug": "made-up-tool-that-does-not-exist",
                    "lane": "hosted",
                    "note": "invented",
                },
                {
                    "slug": "python-seo-analyzer",
                    "lane": "selfhost",
                    "note": "crawls the site",
                },
            ],
        }
        with patch("api.stack_assemble._llm_picks", return_value=fake):
            response = api_client.post(
                "/stacks/assemble/",
                {"query": "start SEO"},
                format="json",
            )
        assert response.status_code == 201
        slugs = {
            item.get("slug")
            for lane in response.json()["lanes"]
            for item in lane["items"]
            if item.get("slug")
        }
        assert "made-up-tool-that-does-not-exist" not in slugs
        assert "python-seo-analyzer" in slugs

    def test_missing_stack_404(self, api_client, db):
        response = api_client.get("/stacks/doesnotexist/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestSavePersonStack:
    @patch("api.stack_assemble.smart_search")
    def test_person_can_save_a_subset(self, mock_search, api_client, catalog):
        mock_search.return_value = []
        response = api_client.post(
            "/stacks/",
            {
                "query": "SEO for my SaaS",
                "title": "My SEO stack",
                "lanes": [
                    {
                        "id": "selfhost",
                        "items": [{"slug": "python-seo-analyzer"}],
                    },
                    {
                        "id": "hosted",
                        "items": [{"slug": "seomatic-ai"}, {"slug": "ghost-tool"}],
                    },
                ],
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source"] == "person"
        slugs = {
            item.get("slug")
            for lane in data["lanes"]
            for item in lane["items"]
            if item.get("slug")
        }
        assert slugs == {"python-seo-analyzer", "seomatic-ai"}
        assert "ghost-tool" not in slugs
        assert any(lane["id"] == "worker" for lane in data["lanes"])
