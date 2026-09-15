import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import ToolFactory, ToolSubmissionFactory

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


def _auth(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _user(*, email, is_staff=False):
    return User.objects.create_user(
        username=email,
        email=email,
        password="pass12345",
        is_staff=is_staff,
    )


@pytest.mark.django_db
class TestListingOwnerEdit:
    def test_owner_can_rename_listing(self, api_client):
        owner = _user(email="contact@nitrosend.com")
        tool = ToolFactory(
            name="NitroSend",
            slug="nitrosend",
            description="NitroSend is an email platform.",
            is_featured=False,
        )
        ToolSubmissionFactory(
            name="NitroSend",
            submitter_email="contact@nitrosend.com",
            submitter_name="George Hartley",
            status="approved",
            approved_tool=tool,
        )
        _auth(api_client, owner)

        response = api_client.patch(
            reverse("tool-detail", kwargs={"slug": "nitrosend"}),
            {"name": "Nitrosend"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Nitrosend"
        assert response.data["can_edit"] is True
        tool.refresh_from_db()
        assert tool.name == "Nitrosend"
        assert tool.slug == "nitrosend"
        assert tool.is_featured is False

    def test_owner_cannot_change_editorial_flags(self, api_client):
        owner = _user(email="founder@example.com")
        tool = ToolFactory(name="Acme", slug="acme", is_featured=False, verified=False)
        ToolSubmissionFactory(
            name="Acme",
            submitter_email=owner.email,
            status="approved",
            approved_tool=tool,
        )
        _auth(api_client, owner)

        response = api_client.patch(
            reverse("tool-detail", kwargs={"slug": "acme"}),
            {"name": "Acme", "is_featured": True, "verified": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        tool.refresh_from_db()
        assert tool.is_featured is False
        assert tool.verified is False

    def test_other_user_cannot_edit(self, api_client):
        tool = ToolFactory(name="Acme", slug="acme")
        ToolSubmissionFactory(
            name="Acme",
            submitter_email="owner@example.com",
            status="approved",
            approved_tool=tool,
        )
        stranger = _user(email="stranger@example.com")
        _auth(api_client, stranger)

        response = api_client.patch(
            reverse("tool-detail", kwargs={"slug": "acme"}),
            {"name": "Hacked"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        tool.refresh_from_db()
        assert tool.name == "Acme"

    def test_owner_cannot_delete(self, api_client):
        owner = _user(email="founder@example.com")
        tool = ToolFactory(name="Acme", slug="acme")
        ToolSubmissionFactory(
            name="Acme",
            submitter_email=owner.email,
            status="approved",
            approved_tool=tool,
        )
        _auth(api_client, owner)

        response = api_client.delete(reverse("tool-detail", kwargs={"slug": "acme"}))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert tool.__class__.objects.filter(pk=tool.pk).exists()

    def test_retrieve_can_edit_only_for_owner(self, api_client):
        owner = _user(email="founder@example.com")
        stranger = _user(email="stranger@example.com")
        tool = ToolFactory(name="Acme", slug="acme")
        ToolSubmissionFactory(
            name="Acme",
            submitter_email=owner.email,
            status="approved",
            approved_tool=tool,
        )

        public = api_client.get(reverse("tool-detail", kwargs={"slug": "acme"}))
        assert public.status_code == status.HTTP_200_OK
        assert public.data["can_edit"] is False

        _auth(api_client, owner)
        mine = api_client.get(reverse("tool-detail", kwargs={"slug": "acme"}))
        assert mine.data["can_edit"] is True

        _auth(api_client, stranger)
        other = api_client.get(reverse("tool-detail", kwargs={"slug": "acme"}))
        assert other.data["can_edit"] is False

    def test_me_includes_owned_listings(self, api_client):
        owner = _user(email="contact@nitrosend.com")
        tool = ToolFactory(name="Nitrosend", slug="nitrosend")
        ToolSubmissionFactory(
            name="Nitrosend",
            submitter_email="contact@nitrosend.com",
            status="approved",
            approved_tool=tool,
        )
        _auth(api_client, owner)
        response = api_client.get(reverse("current_user"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["owned_listings"] == [
            {"slug": "nitrosend", "name": "Nitrosend"}
        ]
