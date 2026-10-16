import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import EmailVerificationCode, ToolSubmission

User = get_user_model()

PAYLOAD = {
    "name": "Submitted Tool",
    "description": "A community submission",
    "website": "https://example.com",
    "submitter_email": "founder@example.com",
    "submitter_name": "Ada Lovelace",
}


def _code_from_outbox() -> str:
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


def _request_code(client, email="founder@example.com"):
    return client.post(
        reverse("submission-request-email-code"),
        {"email": email},
        format="json",
    )


@pytest.mark.django_db
def test_logged_in_session_can_request_a_code_without_csrf():
    User.objects.create_user(
        username="session@example.com",
        email="session@example.com",
        password="pass12345",
    )
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username="session@example.com", password="pass12345")
    response = _request_code(client, "founder@example.com")
    assert response.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 1


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _skip_submission_enrichment(monkeypatch):
    monkeypatch.setattr(
        "api.ai_enrichment.enrich_tool_data",
        lambda *args, **kwargs: {"tags": ["manual"]},
    )


@pytest.mark.django_db
def test_request_code_emails_a_code_and_hides_it_from_the_response(api_client):
    response = _request_code(api_client)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["detail"] == "Verification code sent."
    assert "code" not in response.data
    body = mail.outbox[-1].body
    assert _code_from_outbox() not in str(response.data)
    assert "One9Founders" in body
    assert mail.outbox[-1].to == ["founder@example.com"]


@pytest.mark.django_db
def test_verified_submitter_creates_submission_and_account(api_client):
    _request_code(api_client, "Founder@Example.com")
    response = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": _code_from_outbox()},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["account_created"] is True
    assert response.data["email_verified"] is True
    assert response.data["submitter_email"] == "founder@example.com"

    submission = ToolSubmission.objects.get()
    assert submission.submitter_email == "founder@example.com"
    user = User.objects.get(email="founder@example.com")
    assert user.username == "founder@example.com"
    assert user.first_name == "Ada"
    assert user.last_name == "Lovelace"
    assert user.email_verified_at is not None
    assert user.has_usable_password() is False
    assert user.profile_completed is False
    code = EmailVerificationCode.objects.get()
    assert code.consumed_at is not None


@pytest.mark.django_db
def test_existing_account_is_verified_without_replacing_the_password(api_client):
    user = User.objects.create_user(
        username="founder@example.com",
        email="founder@example.com",
        password="already-set",
        first_name="Kept",
    )
    _request_code(api_client)
    response = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": _code_from_outbox()},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["account_created"] is False
    user.refresh_from_db()
    assert user.check_password("already-set")
    assert user.first_name == "Kept"
    assert user.email_verified_at is not None
    assert User.objects.filter(email="founder@example.com").count() == 1


@pytest.mark.django_db
def test_wrong_code_does_not_create_a_submission_or_account(api_client):
    _request_code(api_client)
    response = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": "000000"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert ToolSubmission.objects.count() == 0
    assert User.objects.filter(email="founder@example.com").count() == 0
    assert EmailVerificationCode.objects.get().consumed_at is None


@pytest.mark.django_db
def test_code_cannot_be_reused(api_client):
    _request_code(api_client)
    code = _code_from_outbox()
    first = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": code},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED
    second = api_client.post(
        reverse("submission-list"),
        {
            **PAYLOAD,
            "name": "Another Tool",
            "website": "https://another.example.com",
            "email_code": code,
        },
        format="json",
    )
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert ToolSubmission.objects.count() == 1


@pytest.mark.django_db
def test_expired_code_is_rejected(api_client):
    _request_code(api_client)
    code = _code_from_outbox()
    row = EmailVerificationCode.objects.get()
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save(update_fields=["expires_at"])
    response = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": code},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert ToolSubmission.objects.count() == 0


@pytest.mark.django_db
def test_too_many_wrong_attempts_lock_the_code(api_client):
    _request_code(api_client)
    real_code = _code_from_outbox()
    wrong_code = "111111" if real_code != "111111" else "222222"
    for _ in range(5):
        response = api_client.post(
            reverse("submission-list"),
            {**PAYLOAD, "email_code": wrong_code},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    locked = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": real_code},
        format="json",
    )
    assert locked.status_code == status.HTTP_400_BAD_REQUEST
    assert "Too many attempts" in locked.data["detail"]
    assert User.objects.filter(email="founder@example.com").count() == 0


@pytest.mark.django_db
def test_resend_is_rate_limited_until_the_window_passes(api_client):
    assert _request_code(api_client).status_code == status.HTTP_200_OK
    again = _request_code(api_client)
    assert again.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    row = EmailVerificationCode.objects.get()
    row.created_at = timezone.now() - timedelta(seconds=61)
    row.save(update_fields=["created_at"])
    resent = _request_code(api_client)
    assert resent.status_code == status.HTTP_200_OK
    assert EmailVerificationCode.objects.filter(consumed_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_email_send_failure_does_not_keep_a_code(api_client, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("ses down")

    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", boom)
    response = _request_code(api_client)
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert EmailVerificationCode.objects.count() == 0


@pytest.mark.django_db
def test_invalid_submission_does_not_consume_the_code(api_client):
    _request_code(api_client)
    code = _code_from_outbox()
    rejected = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "website": "not-a-url", "email_code": code},
        format="json",
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert EmailVerificationCode.objects.get().consumed_at is None
    accepted = api_client.post(
        reverse("submission-list"),
        {**PAYLOAD, "email_code": code},
        format="json",
    )
    assert accepted.status_code == status.HTTP_201_CREATED
