import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import CategoryFactory, ToolFactory

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin@example.com",
        email="admin@example.com",
        password="pass12345",
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="user@example.com",
        email="user@example.com",
        password="pass12345",
        is_staff=False,
    )


def _auth(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.mark.django_db
class TestToolWriteAuth:
    def test_list_tools_remains_public(self, api_client):
        ToolFactory()
        response = api_client.get(reverse("tool-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_create_tool_unauthenticated_returns_404(self, api_client):
        url = reverse("tool-list")
        response = api_client.post(
            url,
            {"name": "Secret Tool", "description": "Should not be created"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not response.data.get("name")

    def test_create_tool_regular_user_returns_404(self, api_client, regular_user):
        _auth(api_client, regular_user)
        response = api_client.post(
            reverse("tool-list"),
            {"name": "Secret Tool", "description": "Should not be created"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_tool_staff_succeeds(self, api_client, staff_user):
        _auth(api_client, staff_user)
        category = CategoryFactory()
        response = api_client.post(
            reverse("tool-list"),
            {
                "name": "Staff Tool",
                "description": "Created by staff",
                "categories": [category.id],
                "tags": ["ai"],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Staff Tool"

    def test_add_tool_unauthenticated_returns_404(self, api_client):
        response = api_client.post(
            reverse("tool-add"),
            {"name": "New Tool", "description": "A new AI tool"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_tool_staff_succeeds(self, api_client, staff_user):
        _auth(api_client, staff_user)
        category = CategoryFactory()
        response = api_client.post(
            reverse("tool-add"),
            {
                "name": "New Tool",
                "description": "A new AI tool",
                "website": "https://example.com",
                "categories": [category.id],
                "tags": ["ai"],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Tool"

    def test_update_tool_unauthenticated_returns_404(self, api_client):
        tool = ToolFactory()
        response = api_client.patch(
            reverse("tool-detail", kwargs={"slug": tool.slug}),
            {"description": "hacked"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_tool_unauthenticated_returns_404(self, api_client):
        tool = ToolFactory()
        response = api_client.delete(reverse("tool-detail", kwargs={"slug": tool.slug}))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_jwt_on_create_returns_404_not_401(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        response = api_client.post(
            reverse("tool-list"),
            {"name": "Nope", "description": "Nope"},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestSubmissionAuth:
    def test_create_submission_remains_public(self, api_client):
        response = api_client.post(
            reverse("submission-list"),
            {
                "name": "Submitted Tool",
                "description": "A community submission",
                "website": "https://example.com",
                "submitter_email": "founder@example.com",
                "submitter_name": "Founder",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_list_submissions_unauthenticated_returns_404(self, api_client):
        response = api_client.get(reverse("submission-list"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_me_includes_is_staff(self, api_client, staff_user):
        _auth(api_client, staff_user)
        response = api_client.get(reverse("current_user"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_staff"] is True
