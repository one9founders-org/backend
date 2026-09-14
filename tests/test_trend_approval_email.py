import pytest
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestTrendApprovalEmail:
    def test_requires_pipeline_key(self, api_client):
        url = reverse("trend-approval-email")
        response = api_client.post(
            url,
            {"drafts": [{"title": "iOS 27", "filename": "x.mdx"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_sends_digest_with_pipeline_key(self, api_client, settings):
        settings.PIPELINE_API_KEY = "test-pipeline-key"
        settings.TREND_APPROVAL_EMAIL = "amit@example.com"
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        url = reverse("trend-approval-email")
        response = api_client.post(
            url,
            {
                "drafts": [
                    {
                        "title": "iOS 27 Features — What It Means for AI Tools & Founders",
                        "filename": "2026-09-14-ios-27-features.mdx",
                        "geo": "US",
                        "approxTraffic": "2000+",
                        "topic": "iOS 27 Features",
                        "summary": "Trending draft summary",
                        "source": "https://trends.google.com/example",
                    }
                ],
                "note": "from unit test",
            },
            format="json",
            HTTP_X_PIPELINE_KEY="test-pipeline-key",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
        assert response.data["recipients"] == ["amit@example.com"]
        assert len(mail.outbox) == 1
        assert "trend blog draft" in mail.outbox[0].subject.lower()
        assert "iOS 27" in mail.outbox[0].body
        assert "amit@example.com" in mail.outbox[0].to
