from unittest.mock import patch

import pytest
from django.core.management import call_command

from agents.discovery.ingest import ingest_candidates
from agents.discovery.normalize import (
    infer_category,
    map_pricing,
    normalize_string_list,
    should_skip_category,
)
from agents.discovery.pipeline import run_agent_scrape
from agents.discovery.sources import _product_name_from_title, parse_awesome_markdown
from agents.models import AgentCategory, AIAgent
from tests.factories import AgentCategoryFactory, AIAgentFactory


class TestNormalize:
    def test_pipe_and_newline_feature_lists(self):
        assert normalize_string_list("A || B || C") == ["A", "B", "C"]
        assert normalize_string_list("A\nB\nC") == ["A", "B", "C"]
        assert normalize_string_list(["A", "A", "B"]) == ["A", "B"]
        assert normalize_string_list(None) == []

    def test_pricing_and_nsfw(self):
        assert map_pricing("freemium") == "Freemium"
        assert map_pricing("open source") == "Free"
        assert should_skip_category("NSFW") is True
        assert should_skip_category("Coding Agent") is False

    def test_infer_category_from_text(self):
        assert infer_category("autonomous coding agent for GitHub issues") == (
            "Coding Agent"
        )
        assert infer_category("voice agent for call centers") == "Voice AI Agents"


class TestParseAwesomeMarkdown:
    def test_parses_heading_and_list_entries(self):
        markdown = """
# Awesome AI Agents

## Coding Agents

- [OpenHands](https://github.com/All-Hands-AI/OpenHands) - Autonomous software engineer
- [Devin](https://devin.ai) — Fully autonomous AI software engineer

## [Aider](https://aider.chat/)

### Category
Coding Agent

### Description
- Pair programming in your terminal

### Links
- [GitHub](https://github.com/Aider-AI/aider)

## Learning Resources

- [A random course](https://example.com/course) - not an agent
"""
        agents = parse_awesome_markdown(markdown)
        names = {item["name"] for item in agents}
        assert "OpenHands" in names
        assert "Devin" in names
        assert "Aider" in names
        assert "A random course" not in names
        aider = next(item for item in agents if item["name"] == "Aider")
        assert aider["github_url"] == "https://github.com/Aider-AI/aider"
        assert aider["website"] == "https://aider.chat/"
        openhands = next(item for item in agents if item["name"] == "OpenHands")
        assert openhands["category_label"] == "Coding Agent"

    def test_skips_directory_hosts(self):
        markdown = "- [Mirror](https://aiagentsdirectory.com/agent/foo) - copy"
        assert parse_awesome_markdown(markdown) == []

    def test_rejects_headline_titles(self):
        assert _product_name_from_title("What happens when an AI agent stops?") == ""
        assert _product_name_from_title("Ask HN: Best agents?") == ""
        assert _product_name_from_title("Show HN: OpenHands") == "OpenHands"


@pytest.mark.django_db
class TestIngestCandidates:
    def test_creates_and_dedupes_by_website(self):
        result = ingest_candidates(
            [
                {
                    "name": "OpenHands",
                    "slug": "openhands",
                    "website": "https://github.com/All-Hands-AI/OpenHands",
                    "source": "github",
                    "source_rank": 50,
                    "category_label": "Coding Agent",
                    "short_description": "Autonomous software engineer",
                    "long_description": "",
                    "key_features": [],
                    "use_cases": [],
                    "popularity_score": 40,
                    "upvotes": 40,
                    "views": 0,
                    "github_url": "https://github.com/All-Hands-AI/OpenHands",
                    "access": "Open Source",
                    "pricing_model": "Free",
                    "industry": "",
                    "logo_url": "",
                    "image_url": "",
                    "video_url": "",
                    "twitter_url": "",
                    "linkedin_url": "",
                    "discord_url": "",
                    "email": "",
                    "is_featured": False,
                    "external_id": "github:All-Hands-AI/OpenHands",
                    "created_at": None,
                },
                {
                    "name": "OpenHands",
                    "slug": "openhands",
                    "website": "https://www.github.com/All-Hands-AI/OpenHands/",
                    "source": "awesome",
                    "source_rank": 70,
                    "category_label": "Coding Agent",
                    "short_description": "Open-source Devin alternative",
                    "long_description": "Longer writeup",
                    "key_features": [],
                    "use_cases": [],
                    "popularity_score": 10,
                    "upvotes": 0,
                    "views": 0,
                    "github_url": "https://github.com/All-Hands-AI/OpenHands",
                    "access": "Open Source",
                    "pricing_model": "Free",
                    "industry": "",
                    "logo_url": "",
                    "image_url": "",
                    "video_url": "",
                    "twitter_url": "",
                    "linkedin_url": "",
                    "discord_url": "",
                    "email": "",
                    "is_featured": False,
                    "external_id": None,
                    "created_at": None,
                },
            ]
        )
        assert result["created"] == 1
        assert AIAgent.objects.count() == 1
        agent = AIAgent.objects.get()
        assert agent.source == "awesome"
        assert agent.short_description == "Open-source Devin alternative"
        assert AgentCategory.objects.filter(slug="coding-agent").exists()

    def test_refresh_does_not_clobber_richer_listing(self):
        category = AgentCategoryFactory(label="Coding Agent", slug="coding-agent")
        existing = AIAgentFactory(
            name="Aider",
            slug="aider",
            website="https://aider.chat",
            source="aiagentsdirectory",
            short_description="Pair programming agent",
            long_description="Full directory writeup",
            category=category,
            category_name="Coding Agent",
            popularity_score=900,
        )
        result = ingest_candidates(
            [
                {
                    "name": "Aider",
                    "slug": "aider",
                    "website": "https://aider.chat/",
                    "source": "github",
                    "source_rank": 50,
                    "category_label": "Coding Agent",
                    "short_description": "README one-liner",
                    "long_description": "README one-liner",
                    "key_features": [],
                    "use_cases": [],
                    "popularity_score": 12,
                    "upvotes": 12,
                    "views": 0,
                    "github_url": "https://github.com/Aider-AI/aider",
                    "access": "Open Source",
                    "pricing_model": "Free",
                    "industry": "",
                    "logo_url": "",
                    "image_url": "",
                    "video_url": "",
                    "twitter_url": "",
                    "linkedin_url": "",
                    "discord_url": "",
                    "email": "",
                    "is_featured": False,
                    "external_id": "github:Aider-AI/aider",
                    "created_at": None,
                }
            ]
        )
        existing.refresh_from_db()
        assert result["created"] == 0
        assert existing.short_description == "Pair programming agent"
        assert existing.source == "aiagentsdirectory"
        assert existing.github_url == "https://github.com/Aider-AI/aider"
        assert existing.popularity_score == 900

    def test_same_source_refresh_updates_copy(self):
        AIAgentFactory(
            name="Old Name",
            slug="agentman",
            website="https://agentman.ai",
            source="aiagentsdirectory",
            short_description="old",
            external_id="abc123",
        )
        result = ingest_candidates(
            [
                {
                    "name": "Agentman",
                    "slug": "agentman",
                    "website": "https://agentman.ai",
                    "source": "aiagentsdirectory",
                    "source_rank": 100,
                    "category_label": "AI Agents Platform",
                    "short_description": "new blurb",
                    "long_description": "new long",
                    "key_features": ["Skills"],
                    "use_cases": ["Clinics"],
                    "popularity_score": 50,
                    "upvotes": 5,
                    "views": 100,
                    "github_url": "",
                    "access": "Closed Source",
                    "pricing_model": "Freemium",
                    "industry": "Horizontal",
                    "logo_url": "",
                    "image_url": "",
                    "video_url": "",
                    "twitter_url": "",
                    "linkedin_url": "",
                    "discord_url": "",
                    "email": "",
                    "is_featured": False,
                    "external_id": "abc123",
                    "created_at": None,
                }
            ]
        )
        agent = AIAgent.objects.get(slug="agentman")
        assert result["updated"] == 1
        assert agent.name == "Agentman"
        assert agent.short_description == "new blurb"
        assert agent.key_features == ["Skills"]


@pytest.mark.django_db
class TestScrapeCommand:
    def test_dry_run_does_not_write(self):
        with patch(
            "agents.discovery.pipeline.fetch_all_sources",
            return_value={
                "github": [
                    {
                        "name": "CrewAI",
                        "slug": "crewai",
                        "website": "https://github.com/crewAIInc/crewAI",
                        "source": "github",
                        "source_rank": 50,
                        "category_label": "AI Agents Frameworks",
                        "short_description": "Multi-agent framework",
                        "long_description": "",
                        "key_features": [],
                        "use_cases": [],
                        "popularity_score": 20,
                        "upvotes": 20,
                        "views": 0,
                        "github_url": "https://github.com/crewAIInc/crewAI",
                        "access": "Open Source",
                        "pricing_model": "Free",
                        "industry": "",
                        "logo_url": "",
                        "image_url": "",
                        "video_url": "",
                        "twitter_url": "",
                        "linkedin_url": "",
                        "discord_url": "",
                        "email": "",
                        "is_featured": False,
                        "external_id": "github:crewAIInc/crewAI",
                        "created_at": None,
                    }
                ]
            },
        ):
            summary = run_agent_scrape(sources=("github",), dry_run=True)
        assert summary["created"] == 1
        assert AIAgent.objects.count() == 0

    def test_command_rejects_unknown_source(self):
        with pytest.raises(Exception):
            call_command("scrape_agents", sources="not-a-source")
