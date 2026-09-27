"""Catalog query, identity, events, submissions, and discovery safeguards."""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from agents.discovery.normalize import map_access
from agents.models import AIAgent
from agents.serializers import display_access_label, popularity_payload
from api.discovery.facts import Facts
from api.discovery.pipeline import (
    select_with_source_budget,
    structured_refresh_updates,
)
from api.discovery.quality_gate import usefulness_gaps
from api.discovery.url_safety import host_is_blocked
from api.models import CatalogEvent, ServiceInquiry, Tool, ToolClick, ToolSubmission


@pytest.fixture
def api_client():
    return APIClient()


def _tool(name, **kwargs):
    defaults = {
        "description": f"{name} helps founders complete a specific workflow with AI.",
        "short_description": name,
        "is_active": True,
        "pricing_type": "paid",
    }
    defaults.update(kwargs)
    return Tool.objects.create(name=name, **defaults)


@pytest.mark.django_db
class TestDirectoryQuery:
    def test_filters_and_sort_apply_before_pagination(self, api_client):
        older = _tool(
            "Alpha Mail",
            description="Outbound sales email drafts for founders.",
            pricing_type="free",
        )
        newer = _tool(
            "Beta Support",
            description="Customer support helpdesk replies for a team inbox.",
            pricing_type="paid",
        )
        Tool.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        Tool.objects.filter(pk=newer.pk).update(created_at=timezone.now())

        response = api_client.get(
            "/tools/",
            {"q": "support", "pricing_type": "paid", "ordering": "-created_at", "page_size": 1},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["results"][0]["name"] == "Beta Support"
        assert payload["results"][0]["preferred_path"] == f"/tool/{newer.slug}"

    def test_relevance_orders_name_matches_first(self, api_client):
        _tool("Video Notes", description="A generic notebook with video in the body.")
        exact = _tool("Video", description="Unrelated description about audio.")
        response = api_client.get("/tools/", {"q": "Video", "ordering": "relevance"})
        names = [row["name"] for row in response.json()["results"]]
        assert names[0] == exact.name

    def test_job_filter_reaches_past_the_first_page(self, api_client):
        for index in range(3):
            _tool(f"Other {index}", description="Writing assistant for blog posts.")
        match = _tool(
            "Inbox Helper",
            description="Customer support helpdesk for startup teams.",
            pricing_type="free",
        )
        response = api_client.get(
            "/tools/",
            {
                "job_cluster": "support",
                "pricing_type": "free",
                "page_size": 20,
            },
        )
        assert response.status_code == 200
        names = [row["name"] for row in response.json()["results"]]
        assert match.name in names
        assert all(not name.startswith("Other") for name in names)

    def test_unknown_ordering_is_ignored(self, api_client):
        _tool("Safe Order")
        response = api_client.get("/tools/", {"ordering": "website;drop"})
        assert response.status_code == 200
        assert response.json()["count"] >= 1


@pytest.mark.django_db
class TestIdentity:
    def test_shared_slug_is_removed_from_the_tool_sitemap(self, api_client):
        tool = _tool(
            "15Minutes",
            slug="15minutes",
            description="A long enough description for the indexability gate. " * 8,
            pricing_type="freemium",
            use_cases=["reading"],
        )
        AIAgent.objects.create(
            slug="15minutes",
            name="15Minutes",
            short_description="Book summaries and analysis for busy founders and operators.",
            website="https://www.15minutes.ai/",
        )
        response = api_client.get(reverse("tool-sitemap"))
        slugs = {row["slug"] for row in response.json()["results"]}
        assert tool.slug not in slugs
        detail = api_client.get(f"/tools/{tool.slug}/")
        assert detail.json()["preferred_path"] == "/agents/15minutes"


class TestPresentation:
    def test_popularity_out_of_range_is_not_a_percentage(self):
        assert popularity_payload(106) == {"state": "unbounded", "value": 106}
        assert popularity_payload(0)["state"] == "unavailable"
        assert popularity_payload(40) == {"state": "bounded", "value": 40}

    def test_open_source_requires_a_repository(self):
        commercial = AIAgent(access="Open Source", github_url="", name="Filmora")
        sourced = AIAgent(
            access="Open Source",
            github_url="https://github.com/example/repo",
            name="Repo",
        )
        assert display_access_label(commercial) is None
        assert display_access_label(sourced) == "Open Source"

    def test_map_access_does_not_infer_open_source_from_github(self):
        assert map_access("", "https://github.com/wondershare/filmora") == ""
        assert map_access("Open Source", "") == "Open Source"


class TestDiscoveryPolicy:
    def test_usefulness_keeps_unknown_pricing_unknown(self):
        facts = Facts(category="Support", meta_description="Replies to tickets")
        assert usefulness_gaps("Helper", facts, "https://helper.example") == []
        assert any(
            "capability" in gap
            for gap in usefulness_gaps("Helper", Facts(), "https://helper.example")
        )

    def test_source_budget_leaves_room_for_a_second_source(self):
        ranked = [{"sourceType": "github", "name": f"g{i}"} for i in range(6)]
        ranked += [{"sourceType": "hackernews", "name": "hn"}]
        selected, deferred = select_with_source_budget(ranked, max_new=4, cap_ratio=0.5)
        sources = [row["sourceType"] for row in selected]
        assert "hackernews" in sources
        assert sources.count("github") < 4
        assert len(selected) == 4
        assert deferred

    def test_structured_facts_change_without_a_new_description(self):
        tool = Tool(name="Demo", pricing_type="freemium", free_tier_available=False)
        facts = Facts(pricing="paid", free_tier_available=False, pricing_from=20)
        updates = structured_refresh_updates(tool, facts)
        assert updates["pricing_type"] == "paid"
        assert updates["pricing_from"] == Decimal("20")

    def test_private_hosts_are_blocked(self):
        assert host_is_blocked("127.0.0.1") is True
        assert host_is_blocked("169.254.169.254") is True
        assert host_is_blocked("metadata.google.internal") is True
        assert host_is_blocked("localhost") is True


@pytest.mark.django_db
class TestRefreshFacts:
    def test_similar_prose_still_saves_pricing(self):
        from api.discovery.pipeline import run_refresh_descriptions

        tool = _tool(
            "Priced",
            website="https://priced.example",
            description="Priced helps teams draft support replies from the inbox.",
            pricing_type="freemium",
        )
        facts = Facts(
            pricing="paid",
            category="Support",
            meta_description="Support drafts",
            pricing_from=30,
            source_text="official",
        )
        with (
            patch("api.discovery.pipeline.fetch_facts", return_value=facts),
            patch(
                "api.discovery.pipeline.generate_description",
                return_value=tool.description,
            ),
            patch(
                "api.discovery.pipeline.passes_quality_gate",
                return_value=(True, []),
            ),
            patch("api.discovery.pipeline._persist_first_party_facts", return_value=1),
        ):
            summary = run_refresh_descriptions(limit=5)
        tool.refresh_from_db()
        assert tool.pricing_type == "paid"
        assert tool.pricing_from == Decimal("30")
        assert summary["updated"] == 1
        assert summary["noop_skipped"] == 0


@pytest.mark.django_db
class TestSubmissionsAndEvents:
    def test_submission_is_saved_when_enrichment_fails(
        self, api_client, django_capture_on_commit_callbacks
    ):
        with (
            patch(
                "api.ai_enrichment.enrich_tool_data",
                side_effect=RuntimeError("provider down"),
            ),
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = api_client.post(
                    "/submissions/",
                    {
                        "name": "Helper",
                        "description": "Helper drafts replies for a support inbox used by a small team.",
                        "website": "https://helper.example",
                        "submitter_email": "founder@example.com",
                        "submitter_name": "A Founder",
                    },
                    format="json",
                )
        assert response.status_code == 201
        saved = ToolSubmission.objects.get(submitter_email="founder@example.com")
        assert saved.enrichment_status == "failed"
        assert saved.public_token
        status_response = api_client.get(
            "/submissions/status/", {"token": str(saved.public_token)}
        )
        body = status_response.json()
        assert body["moderation_status"] == "pending"
        assert body["facts_verified"] is False

    def test_repeat_submission_does_not_duplicate(self, api_client):
        first = api_client.post(
            "/submissions/",
            {
                "name": "Helper",
                "description": "Helper drafts replies for a support inbox used by a small team.",
                "website": "https://helper.example",
                "submitter_email": "founder@example.com",
                "submitter_name": "A Founder",
            },
            format="json",
        )
        second = api_client.post(
            "/submissions/",
            {
                "name": "Helper",
                "description": "Helper drafts replies for a support inbox used by a small team.",
                "website": "https://helper.example/",
                "submitter_email": "founder@example.com",
                "submitter_name": "A Founder",
            },
            format="json",
        )
        assert first.status_code == 201
        assert second.status_code == 200
        assert ToolSubmission.objects.count() == 1

    def test_event_dedup_and_bot_filter(self, api_client):
        tool = _tool("Tracked")
        event_id = str(uuid.uuid4())
        payload = {
            "event_name": "official_site_click",
            "event_id": event_id,
            "entity_type": "tool",
            "entity_id": tool.id,
            "entity_slug": tool.slug,
            "surface": "tool_card",
            "result_position": 2,
            "query_id": "q1",
            "session_id": "sess",
        }
        first = api_client.post("/track/event/", payload, format="json")
        second = api_client.post("/track/event/", payload, format="json")
        assert first.status_code == 201
        assert second.status_code == 200
        assert CatalogEvent.objects.count() == 1
        assert ToolClick.objects.filter(tool=tool, counts_for_ranking=True).count() == 1

        bot = api_client.post(
            "/track/event/",
            {**payload, "event_id": str(uuid.uuid4())},
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)",
        )
        assert bot.status_code == 201
        assert bot.json()["counts_for_ranking"] is False

    def test_service_inquiry_validates_and_persists(self, api_client):
        bad = api_client.post(
            "/services/inquiries/",
            {"offer": "workflow_audit", "workflow": "short"},
            format="json",
        )
        assert bad.status_code == 400
        ok = api_client.post(
            "/services/inquiries/",
            {
                "offer": "workflow_audit",
                "workflow": "Support replies are copied between three inboxes.",
                "current_tools": "Gmail, a shared sheet",
                "team_context": "Four people",
                "desired_outcome": "One queue with drafts",
                "contact_name": "A Founder",
                "contact_email": "founder@example.com",
            },
            format="json",
        )
        assert ok.status_code == 201
        assert ServiceInquiry.objects.count() == 1
        honeypot = api_client.post(
            "/services/inquiries/",
            {
                "offer": "maintenance",
                "workflow": "A long enough workflow description.",
                "desired_outcome": "Keep it running",
                "contact_name": "Bot",
                "contact_email": "bot@example.com",
                "website": "https://spam.example",
            },
            format="json",
        )
        assert honeypot.status_code == 201
        assert ServiceInquiry.objects.filter(contact_email="bot@example.com").count() == 0
