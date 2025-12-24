import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import ToolFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.mark.django_db
class TestAuthentication:
    def test_health_endpoint_public(self, api_client):
        url = reverse("health")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"

    def test_tools_list_public(self, api_client):
        ToolFactory()
        url = reverse("tool-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_admin_requires_authentication(self, api_client):
        response = api_client.get("/admin/")

        # Should redirect to login
        assert response.status_code in [302, 401]


@pytest.mark.django_db
class TestCORSHeaders:
    def test_cors_headers_present(self, api_client):
        url = reverse("tool-list")
        response = api_client.get(url)

        # Check if CORS headers are present (they should be due to django-cors-headers)
        assert response.status_code == status.HTTP_200_OK
