import json
import logging
import time

import anthropic
from django.conf import settings
from django.core.management.base import BaseCommand

from research_papers.models import Paper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enrich papers with AI-generated summaries, tags, and difficulty"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of papers to enrich per run",
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        if not api_key:
            self.stdout.write(self.style.ERROR("ANTHROPIC_API_KEY not set in settings"))
            return

        client = anthropic.Anthropic(api_key=api_key)
        limit = options["limit"]

        papers = Paper.objects.filter(is_enriched=False).order_by("-published_at")[
            :limit
        ]
        self.stdout.write(f"Enriching {papers.count()} papers...")

        enriched = 0
        failed = 0

        for paper in papers:
            try:
                prompt = (
                    "Summarize this AI paper for a non-researcher in 2-3 sentences. "
                    "Also return category tags and difficulty.\n\n"
                    f"Title: {paper.title}\n"
                    f"Abstract: {paper.abstract}\n\n"
                    'Return JSON: {"summary": "...", "tags": ["RAG", "agents", ...], '
                    '"difficulty": "beginner|intermediate|advanced"}'
                )

                message = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )

                response_text = message.content[0].text.strip()

                # Clean potential markdown code block wrapping
                if response_text.startswith("```"):
                    response_text = response_text.split("\n", 1)[-1]
                    if response_text.endswith("```"):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()

                data = json.loads(response_text)

                paper.ai_summary = data.get("summary", "")
                paper.ai_tags = data.get("tags", [])
                paper.ai_difficulty = data.get("difficulty", "intermediate")
                paper.is_enriched = True
                paper.save(
                    update_fields=[
                        "ai_summary",
                        "ai_tags",
                        "ai_difficulty",
                        "is_enriched",
                    ]
                )
                enriched += 1

                # Rate limiting
                time.sleep(1)

            except json.JSONDecodeError as e:
                logger.warning("JSON parse error for paper %s: %s", paper.arxiv_id, e)
                failed += 1
                time.sleep(1)
            except Exception as e:
                logger.warning("Error enriching paper %s: %s", paper.arxiv_id, e)
                failed += 1
                time.sleep(1)

        self.stdout.write(
            self.style.SUCCESS(f"Enriched {enriched} papers, {failed} failed")
        )
