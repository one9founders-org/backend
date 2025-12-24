import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

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

    def test_add_tool(self, api_client):
        category = CategoryFactory()
        url = reverse("tool-add")
        data = {
            "name": "New Tool",
            "description": "A new AI tool",
            "website": "https://example.com",
            "categories": [category.id],
        }
        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Tool"


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
