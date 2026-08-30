import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.fintech import seed_credit_preview, seed_kyc_preview
from api.models import FintechRating, Tool


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestFintechRatingsAPI:
    def test_kyc_stack_returns_three_vendors_with_cited_passes(self, api_client):
        seed_kyc_preview()
        url = reverse("fintech-ratings")
        response = api_client.get(url, {"stack": "kyc"})

        assert response.status_code == status.HTTP_200_OK
        body = response.data
        assert body["stack"] == "kyc"
        assert body["method"] == "published_evidence"
        assert body["hands_on"] is False
        assert body["count"] == 3

        by_slug = {row["slug"]: row for row in body["results"]}
        assert set(by_slug) == {"signzy", "hyperverge", "idfy"}

        signzy = by_slug["signzy"]["assessment_detail"]
        assert signzy["hands_on"] is False
        assert signzy["criteria"]["dataLocalization"]["result"] == "pass"
        assert signzy["criteria"]["dataLocalization"]["evidence_url"]
        assert signzy["criteria"]["dataLocalization"]["evidence_label"]
        assert signzy["criteria"]["consentManagement"]["result"] == "unknown"
        assert signzy["criteria"]["consentManagement"]["evidence_url"] is None
        assert "consentManagement" in signzy["unassessed"]

        hyperverge = by_slug["hyperverge"]["assessment_detail"]
        assert hyperverge["criteria"]["dataLocalization"]["result"] == "unknown"
        assert hyperverge["criteria"]["securityCerts"]["result"] == "pass"
        assert hyperverge["criteria"]["securityCerts"]["evidence_url"]

    def test_unknown_stack_is_400(self, api_client):
        url = reverse("fintech-ratings")
        response = api_client.get(url, {"stack": "payroll"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_credit_stack_returns_three_vendors_with_cited_passes(self, api_client):
        seed_credit_preview()
        url = reverse("fintech-ratings")
        response = api_client.get(url, {"stack": "credit"})
        assert response.status_code == status.HTTP_200_OK
        body = response.data
        assert body["stack"] == "credit"
        assert body["count"] == 3
        by_slug = {row["slug"]: row for row in body["results"]}
        assert set(by_slug) == {"perfios", "scienaptic", "finbox"}
        perfios = by_slug["perfios"]["assessment_detail"]
        assert perfios["criteria"]["securityCerts"]["result"] == "pass"
        assert perfios["criteria"]["securityCerts"]["evidence_url"]
        assert perfios["criteria"]["biasTesting"]["result"] == "unknown"
        assert perfios["criteria"]["biasTesting"]["evidence_url"] is None
        finbox = by_slug["finbox"]["assessment_detail"]
        assert finbox["criteria"]["securityCerts"]["result"] == "pass"
        assert finbox["criteria"]["dataLocalization"]["result"] == "unknown"

    def test_empty_fraud_stack_is_honest(self, api_client):
        seed_kyc_preview()
        url = reverse("fintech-ratings")
        response = api_client.get(url, {"stack": "fraud"})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
        assert response.data["results"] == []

    def test_pass_without_url_rejected(self):
        seed_kyc_preview()
        row = FintechRating.objects.filter(result="pass").first()
        row.evidence_url = ""
        with pytest.raises(ValidationError):
            row.full_clean()

    def test_does_not_write_directory_scores(self):
        seed_kyc_preview()
        tool = Tool.objects.get(slug="signzy")
        assert tool.overall_score is None
        assert tool.security_criterion_score is None
        assert tool.criteria_completed == 0
        assert tool.assessment_detail in ({}, None)
