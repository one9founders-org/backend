import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.tool_stats import TOOL_STATS_CACHE_KEY
from tests.factories import (
    CategoryFactory,
    NewsletterSubscriptionFactory,
    ReviewFactory,
    ToolFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestToolAPI:
    def test_list_tools(self, api_client):
        ToolFactory.create_batch(3)
        url = reverse("tool-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    def test_retrieve_tool(self, api_client):
        tool = ToolFactory()
        url = reverse("tool-detail", kwargs={"slug": tool.slug})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == tool.name

    def test_search_tools(self, api_client):
        ToolFactory(name="ChatGPT", description="AI assistant")
        ToolFactory(name="Midjourney", description="Image generator")

        url = reverse("tool-search")
        response = api_client.post(url, {"query": "AI assistant"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 0

    def test_add_tool_requires_staff(self, api_client):
        url = reverse("tool-add")
        data = {
            "name": "New Tool",
            "description": "A new AI tool",
            "website": "https://example.com",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_exposes_assessment_fields(self, api_client):
        ToolFactory(
            name="RatedField Tool",
            criteria_completed=7,
            overall_score=3.8,
            security_criterion_score=14,
            assessment_detail={"version": 1, "hands_on": False},
        )
        response = api_client.get(reverse("tool-list"))
        row = response.data["results"][0]
        assert row["criteria_completed"] == 7
        assert row["rating_status"] == "PROVISIONAL"
        assert row["security_criterion_score"] == 14
        assert row["assessment_detail"]["hands_on"] is False
        assert row["track"] == "ai_tool"

    def test_rated_filter(self, api_client):
        ToolFactory(name="Full Rated", criteria_completed=10, overall_score=4.2)
        ToolFactory(name="Half Done", criteria_completed=7, overall_score=3.5)
        ToolFactory(name="Untouched", criteria_completed=0)

        provisional = api_client.get(reverse("tool-list"), {"rated": "provisional"})
        names = {row["name"] for row in provisional.data["results"]}
        assert names == {"Half Done"}

        rated = api_client.get(reverse("tool-list"), {"rated": "rated"})
        names = {row["name"] for row in rated.data["results"]}
        assert names == {"Full Rated"}

    def test_overall_score_sort_puts_unrated_last(self, api_client):
        ToolFactory(name="High Score", criteria_completed=7, overall_score=4.2)
        ToolFactory(name="Mid Score", criteria_completed=6, overall_score=3.1)
        ToolFactory(name="No Score", criteria_completed=0, overall_score=None)

        response = api_client.get(reverse("tool-list"), {"ordering": "-overall_score"})
        names = [row["name"] for row in response.data["results"]]
        assert names == ["High Score", "Mid Score", "No Score"]


@pytest.mark.django_db
class TestReviewAPI:
    def test_list_reviews_for_tool(self, api_client):
        tool = ToolFactory()
        ReviewFactory.create_batch(2, tool=tool)

        url = reverse("review-list")
        response = api_client.get(url, {"tool_id": tool.id})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_create_review(self, api_client):
        tool = ToolFactory()
        url = reverse("review-list")
        data = {
            "tool": tool.id,
            "user_name": "John Doe",
            "rating": 5,
            "title": "Great tool",
            "comment": "Very helpful",
        }
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["rating"] == 5


@pytest.mark.django_db
class TestToolDirectoryStatsAPI:
    def setup_method(self):
        cache.clear()

    def test_includes_existing_and_new_totals(self, api_client):
        writing = CategoryFactory(name="Writing", slug="writing")
        image = CategoryFactory(name="Image", slug="image")
        ToolFactory(
            name="Writer One",
            categories=[writing],
            criteria_completed=10,
            is_active=True,
        )
        ToolFactory(
            name="Writer Two",
            categories=[writing],
            criteria_completed=7,
            is_active=True,
        )
        ToolFactory(
            name="Hidden Imager",
            categories=[image],
            criteria_completed=0,
            is_active=False,
        )

        response = api_client.get(reverse("tool-directory-stats"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2
        assert response.data["fully_assessed_count"] == 1
        assert response.data["provisionally_assessed_count"] == 1
        assert response.data["total_tools"] == 3
        assert response.data["by_category"] == [
            {"category": "Writing", "count": 2},
        ]

    def test_serves_cached_payload(self, api_client):
        cache.set(
            TOOL_STATS_CACHE_KEY,
            {
                "count": 99,
                "fully_assessed_count": 10,
                "provisionally_assessed_count": 20,
                "total_tools": 100,
                "by_category": [{"category": "Cached", "count": 99}],
            },
            3600,
        )

        response = api_client.get(reverse("tool-directory-stats"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_tools"] == 100
        assert response.data["by_category"] == [{"category": "Cached", "count": 99}]

    def test_tool_save_busts_cache(self, api_client):
        writing = CategoryFactory(name="Writing", slug="writing")
        ToolFactory(name="First", categories=[writing], is_active=True)

        first = api_client.get(reverse("tool-directory-stats"))
        assert first.data["total_tools"] == 1

        ToolFactory(name="Second", categories=[writing], is_active=True)

        second = api_client.get(reverse("tool-directory-stats"))
        assert second.data["total_tools"] == 2
        assert second.data["by_category"] == [{"category": "Writing", "count": 2}]


@pytest.mark.django_db
class TestCategoryAPI:
    def test_list_categories(self, api_client):
        CategoryFactory.create_batch(3)
        url = reverse("category-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3


@pytest.mark.django_db
class TestNewsletterAPI:
    def test_subscribe_newsletter(self, api_client):
        url = reverse("newsletter-subscribe")
        data = {"email": "test@example.com", "source": "homepage"}
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "test@example.com"

    def test_duplicate_subscription(self, api_client):
        NewsletterSubscriptionFactory(email="test@example.com")

        url = reverse("newsletter-subscribe")
        data = {"email": "test@example.com", "source": "homepage"}
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
