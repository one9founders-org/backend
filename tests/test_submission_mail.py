from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import ToolSubmission
from api.submission_mail import render_listed_email
from tests.factories import ToolFactory


@pytest.mark.django_db
class TestSubmissionListedEmail:
    def test_render_includes_listing_edit_and_social(self):
        tool = ToolFactory(name="Acme AI", slug="acme-ai")
        submission = ToolSubmission.objects.create(
            name="Acme AI",
            description="An AI tool for founders.",
            website="https://acme.example",
            submitter_email="founder@acme.example",
            submitter_name="Priya Sharma",
            status="approved",
            approved_tool=tool,
        )

        subject, text, html = render_listed_email(submission)

        assert "Acme AI" in subject
        assert "https://www.one9founders.com/tool/acme-ai" in text
        assert "https://www.one9founders.com/tool/acme-ai/edit" in text
        assert "founder@acme.example" in text
        assert "linkedin.com/in/amitbhartiya33" in text
        assert "instagram.com/one9founders" in html
        assert "AI and SaaS" in text or "AI &amp; SaaS" in html

    def test_notify_command_dry_run_does_not_send(self):
        tool = ToolFactory(name="Dry Run Tool", slug="dry-run-tool")
        ToolSubmission.objects.create(
            name="Dry Run Tool",
            description="Desc",
            website="https://dry.example",
            submitter_email="dry@example.com",
            submitter_name="Dry",
            status="approved",
            approved_tool=tool,
        )
        out = StringIO()
        with patch("api.submission_mail.send_mail") as send_mail:
            call_command("notify_listed_submissions", stdout=out)

        send_mail.assert_not_called()
        assert "dry-run" in out.getvalue()
        assert (
            ToolSubmission.objects.get(
                submitter_email="dry@example.com"
            ).listed_email_sent_at
            is None
        )

    def test_notify_command_send_marks_sent(self):
        tool = ToolFactory(name="Live Tool", slug="live-tool")
        ToolSubmission.objects.create(
            name="Live Tool",
            description="Desc",
            website="https://live.example",
            submitter_email="live@example.com",
            submitter_name="Live",
            status="approved",
            approved_tool=tool,
        )
        with patch("api.submission_mail.send_mail", return_value=1) as send_mail:
            call_command("notify_listed_submissions", "--send")

        send_mail.assert_called_once()
        submission = ToolSubmission.objects.get(submitter_email="live@example.com")
        assert submission.listed_email_sent_at is not None

    def test_notify_skips_already_sent(self):
        tool = ToolFactory(name="Sent Tool", slug="sent-tool")
        ToolSubmission.objects.create(
            name="Sent Tool",
            description="Desc",
            website="https://sent.example",
            submitter_email="sent@example.com",
            submitter_name="Sent",
            status="approved",
            approved_tool=tool,
            listed_email_sent_at=timezone.now(),
        )
        with patch("api.submission_mail.send_mail") as send_mail:
            call_command("notify_listed_submissions", "--send")

        send_mail.assert_not_called()

    def test_mark_sent_file(self, tmp_path):
        tool = ToolFactory(name="Prior Tool", slug="prior-tool")
        ToolSubmission.objects.create(
            name="Prior Tool",
            description="Desc",
            website="https://prior.example",
            submitter_email="prior@example.com",
            submitter_name="Prior",
            status="approved",
            approved_tool=tool,
        )
        path = tmp_path / "already.txt"
        path.write_text("prior@example.com\n")
        call_command("notify_listed_submissions", f"--mark-sent-file={path}")
        submission = ToolSubmission.objects.get(submitter_email="prior@example.com")
        assert submission.listed_email_sent_at is not None

    def test_community_submissions_endpoint(self):
        tool = ToolFactory(name="Community Tool", slug="community-tool")
        ToolSubmission.objects.create(
            name="Community Tool",
            description="Desc",
            website="https://community.example",
            submitter_email="community@example.com",
            submitter_name="Community",
            status="approved",
            approved_tool=tool,
        )
        ToolFactory(name="Not Submitted", slug="not-submitted")

        client = APIClient()
        url = reverse("community-submitted-tools")
        response = client.get(url)

        assert response.status_code == 200
        slugs = {row["slug"] for row in response.data}
        assert "community-tool" in slugs
        assert "not-submitted" not in slugs
