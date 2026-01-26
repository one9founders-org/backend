"""
AI News Pipeline Engine.
Handles scoring, content generation, and publishing logic.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openai import OpenAI

from .models import News
from .pipeline_models import (
    NewsDraft,
    PipelineConfig,
    PipelineRun,
    PublishedArticle,
    QualifiedNewsItem,
    ScrapedItem,
)

logger = logging.getLogger(__name__)


SCORING_PROMPT = """You are an AI news curator for One9Founders, \
a platform for startup founders.

Evaluate this AI tool/news item for relevance to startup founders:

Title: {title}
Description: {description}
Source: {source}
Category: {category}
Tags: {tags}
Metrics: {metrics}

Score each dimension from 0-100:

1. FOUNDER_RELEVANCE: How useful is this for startup founders?
   - High (70-100): Directly helps founders build, launch, or grow startups
   - Medium (40-69): Generally useful for business/productivity
   - Low (0-39): Consumer-focused or not relevant to founders

2. PRACTICAL_IMPACT: How actionable/practical is this?
   - High (70-100): Can be immediately used to solve real problems
   - Medium (40-69): Interesting but requires effort to apply
   - Low (0-39): Theoretical or limited practical use

3. NOVELTY: How new/innovative is this?
   - High (70-100): First of its kind or significant breakthrough
   - Medium (40-69): Improvement on existing solutions
   - Low (0-39): Similar to many existing tools

Return JSON only:
{{
    "founder_relevance": <0-100>,
    "practical_impact": <0-100>,
    "novelty_score": <0-100>,
    "overall_score": <0-100>,
    "rationale": "<2-3 sentence explanation>"
}}"""


CONTENT_GENERATION_PROMPT = """You are a tech journalist writing for One9Founders, \
a platform for startup founders.

Write a news article about this AI tool/development:

Title: {title}
Description: {description}
Source: {source}
Category: {category}
Original URL: {url}
Metrics: {metrics}

EDITORIAL STYLE:
- Write for busy founders who want actionable insights
- Be concise but informative (300-500 words)
- Use a professional but approachable tone
- Focus on practical implications for startups
- Avoid hype and marketing speak

REQUIRED SECTIONS:
1. HOOK: A compelling opening sentence that grabs attention
2. WHAT IT IS: Brief explanation of the tool/development
3. WHY IT MATTERS: Why founders should care
4. KEY FEATURES: 2-3 most important capabilities
5. FOUNDER TAKEAWAY: One actionable insight or recommendation

Return JSON only:
{{
    "title": "<catchy but informative title, max 70 chars>",
    "excerpt": "<compelling 1-2 sentence preview, max 200 chars>",
    "hook": "<opening hook sentence>",
    "content": "<full article in HTML format with <p>, <h3>, <ul> tags>",
    "why_matters": "<why this matters section>",
    "founder_takeaway": "<key takeaway for founders>",
    "category": "<one of: AI Tools, AI Models, AI News, Productivity, Development>",
    "tags": ["tag1", "tag2", "tag3"],
    "seo_title": "<SEO optimized title, max 60 chars>",
    "seo_description": "<meta description, max 155 chars>"
}}"""


class PipelineEngine:
    """Main engine for the AI News Pipeline."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.scoring_model = "gpt-4o-mini"
        self.generation_model = "gpt-4o-mini"

    def score_item(self, scraped_item: ScrapedItem) -> Optional[QualifiedNewsItem]:
        """Score a scraped item and create a QualifiedNewsItem."""
        try:
            prompt = SCORING_PROMPT.format(
                title=scraped_item.title,
                description=scraped_item.description[:1000],
                source=scraped_item.source,
                category=scraped_item.category,
                tags=", ".join(scraped_item.tags[:10]),
                metrics=json.dumps(scraped_item.metrics),
            )

            response = self.client.chat.completions.create(
                model=self.scoring_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            qualified = QualifiedNewsItem.objects.create(
                scraped_item=scraped_item,
                relevance_score=result.get("overall_score", 0),
                founder_relevance=result.get("founder_relevance", 0),
                practical_impact=result.get("practical_impact", 0),
                novelty_score=result.get("novelty_score", 0),
                scoring_rationale=result.get("rationale", ""),
                scoring_model=self.scoring_model,
            )

            qualified.status = qualified.auto_categorize()
            qualified.save()

            scraped_item.status = "qualified"
            scraped_item.processed_at = timezone.now()
            scraped_item.save()

            logger.info(
                f"Scored item {scraped_item.id}: {qualified.relevance_score} "
                f"-> {qualified.status}"
            )

            return qualified

        except Exception as e:
            logger.error(f"Error scoring item {scraped_item.id}: {e}")
            scraped_item.status = "error"
            scraped_item.status_reason = str(e)
            scraped_item.save()
            return None

    def generate_content(
        self, qualified_item: QualifiedNewsItem
    ) -> Optional[NewsDraft]:
        """Generate article content for a qualified item."""
        try:
            scraped = qualified_item.scraped_item

            prompt = CONTENT_GENERATION_PROMPT.format(
                title=scraped.title,
                description=scraped.description[:2000],
                source=scraped.source,
                category=scraped.category,
                url=scraped.source_url,
                metrics=json.dumps(scraped.metrics),
            )

            response = self.client.chat.completions.create(
                model=self.generation_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            draft = NewsDraft.objects.create(
                qualified_item=qualified_item,
                title=result.get("title", scraped.title)[:255],
                excerpt=result.get("excerpt", "")[:300],
                content=result.get("content", ""),
                hook=result.get("hook", ""),
                why_matters=result.get("why_matters", ""),
                founder_takeaway=result.get("founder_takeaway", ""),
                category=result.get("category", scraped.category),
                tags=result.get("tags", scraped.tags),
                seo_title=result.get("seo_title", "")[:70],
                seo_description=result.get("seo_description", "")[:160],
                featured_image=scraped.images[0] if scraped.images else "",
                generation_model=self.generation_model,
                status="generated",
            )

            logger.info(f"Generated content for item {qualified_item.id}: {draft.id}")
            return draft

        except Exception as e:
            logger.error(f"Error generating content for {qualified_item.id}: {e}")
            return None

    def publish_draft(
        self, draft: NewsDraft, slot: int = 1
    ) -> Optional[PublishedArticle]:
        """Publish a draft to the main News model."""
        if not PipelineConfig.is_publishing_enabled():
            logger.warning("Publishing is disabled via kill-switch")
            return None

        try:
            with transaction.atomic():
                news = News.objects.create(
                    title=draft.title,
                    slug=draft.slug,
                    excerpt=draft.excerpt,
                    content=draft.content,
                    featured_image=draft.featured_image,
                    author="AI News Bot",
                    category=draft.category,
                    tags=draft.tags,
                    is_published=True,
                    published_at=timezone.now(),
                )

                scraped = draft.qualified_item.scraped_item

                published = PublishedArticle.objects.create(
                    draft=draft,
                    news=news,
                    source=scraped.source,
                    original_url=scraped.source_url,
                    relevance_score=draft.qualified_item.relevance_score,
                    publish_slot=slot,
                )

                draft.status = "published"
                draft.published_at = timezone.now()
                draft.save()

                logger.info(f"Published article {news.id}: {news.title}")
                return published

        except Exception as e:
            logger.error(f"Error publishing draft {draft.id}: {e}")
            draft.status = "failed"
            draft.status_reason = str(e)
            draft.save()
            return None

    def get_articles_published_today(self) -> int:
        """Get count of articles published today."""
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return PublishedArticle.objects.filter(published_at__gte=today_start).count()

    def get_next_publish_slot(self) -> Tuple[int, datetime]:
        """Get the next available publish slot and time."""
        today_count = self.get_articles_published_today()
        max_per_day = PipelineConfig.get_max_articles_per_day()

        if today_count >= max_per_day:
            tomorrow = timezone.now().date() + timedelta(days=1)
            return 1, datetime.combine(tomorrow, datetime.min.time().replace(hour=8))

        slot = today_count + 1

        base_times = [8, 10, 12, 14, 16]
        hour = base_times[min(slot - 1, len(base_times) - 1)]

        publish_time = timezone.now().replace(
            hour=hour, minute=0, second=0, microsecond=0
        )

        if publish_time <= timezone.now():
            publish_time = timezone.now() + timedelta(minutes=5)

        return slot, publish_time


class PipelineOrchestrator:
    """Orchestrates the full pipeline execution."""

    def __init__(self):
        self.engine = PipelineEngine()

    def run_scoring(self, source: Optional[str] = None, limit: int = 50) -> PipelineRun:
        """Score unprocessed scraped items."""
        batch_id = f"score_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        run = PipelineRun.objects.create(
            run_type="score",
            source=source or "all",
            batch_id=batch_id,
        )

        try:
            queryset = ScrapedItem.objects.filter(status="scraped")
            if source:
                queryset = queryset.filter(source=source)

            items = queryset[:limit]
            run.items_processed = len(items)

            for item in items:
                result = self.engine.score_item(item)
                if result:
                    run.items_succeeded += 1
                else:
                    run.items_failed += 1

            run.complete(success=True)
            logger.info(
                f"Scoring complete: {run.items_succeeded}/{run.items_processed}"
            )

        except Exception as e:
            run.complete(success=False, error=str(e))
            logger.error(f"Scoring failed: {e}")

        return run

    def run_content_generation(self, limit: int = 10) -> PipelineRun:
        """Generate content for approved items without drafts."""
        batch_id = f"generate_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        run = PipelineRun.objects.create(
            run_type="generate",
            batch_id=batch_id,
        )

        try:
            items = QualifiedNewsItem.objects.filter(
                status__in=["auto_approved", "manually_approved"]
            ).exclude(draft__isnull=False)[:limit]

            run.items_processed = len(items)

            for item in items:
                result = self.engine.generate_content(item)
                if result:
                    run.items_succeeded += 1
                else:
                    run.items_failed += 1

            run.complete(success=True)
            logger.info(
                f"Generation complete: {run.items_succeeded}/{run.items_processed}"
            )

        except Exception as e:
            run.complete(success=False, error=str(e))
            logger.error(f"Content generation failed: {e}")

        return run

    def run_publishing(self, limit: int = 5) -> PipelineRun:
        """Publish ready drafts up to daily limit."""
        batch_id = f"publish_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        run = PipelineRun.objects.create(
            run_type="publish",
            batch_id=batch_id,
        )

        try:
            if not PipelineConfig.is_publishing_enabled():
                run.complete(success=True)
                run.add_log("Publishing disabled via kill-switch", "warning")
                return run

            today_count = self.engine.get_articles_published_today()
            max_per_day = PipelineConfig.get_max_articles_per_day()
            remaining = max_per_day - today_count

            if remaining <= 0:
                run.complete(success=True)
                run.add_log(f"Daily limit reached ({max_per_day})", "info")
                return run

            drafts = NewsDraft.objects.filter(
                status__in=["generated", "ready"]
            ).order_by("-qualified_item__relevance_score")[: min(limit, remaining)]

            run.items_processed = len(drafts)

            for i, draft in enumerate(drafts):
                slot = today_count + i + 1
                result = self.engine.publish_draft(draft, slot)
                if result:
                    run.items_succeeded += 1
                else:
                    run.items_failed += 1

            run.complete(success=True)
            logger.info(
                f"Publishing complete: {run.items_succeeded}/{run.items_processed}"
            )

        except Exception as e:
            run.complete(success=False, error=str(e))
            logger.error(f"Publishing failed: {e}")

        return run

    def run_full_pipeline(
        self,
        source: Optional[str] = None,
        score_limit: int = 50,
        generate_limit: int = 10,
        publish_limit: int = 5,
    ) -> PipelineRun:
        """Run the full pipeline: score -> generate -> publish."""
        batch_id = f"full_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        run = PipelineRun.objects.create(
            run_type="full",
            source=source or "all",
            batch_id=batch_id,
        )

        try:
            run.add_log("Starting scoring phase")
            score_run = self.run_scoring(source, score_limit)
            run.add_log(
                f"Scoring: {score_run.items_succeeded}/{score_run.items_processed}"
            )

            run.add_log("Starting content generation phase")
            gen_run = self.run_content_generation(generate_limit)
            run.add_log(
                f"Generation: {gen_run.items_succeeded}/{gen_run.items_processed}"
            )

            run.add_log("Starting publishing phase")
            pub_run = self.run_publishing(publish_limit)
            run.add_log(
                f"Publishing: {pub_run.items_succeeded}/{pub_run.items_processed}"
            )

            run.items_processed = (
                score_run.items_processed
                + gen_run.items_processed
                + pub_run.items_processed
            )
            run.items_succeeded = (
                score_run.items_succeeded
                + gen_run.items_succeeded
                + pub_run.items_succeeded
            )
            run.items_failed = (
                score_run.items_failed + gen_run.items_failed + pub_run.items_failed
            )

            run.complete(success=True)
            logger.info(f"Full pipeline complete: {run.items_succeeded} total")

        except Exception as e:
            run.complete(success=False, error=str(e))
            logger.error(f"Full pipeline failed: {e}")

        return run


def ingest_scraper_output(
    source: str, items: List[Dict[str, Any]], batch_id: Optional[str] = None
) -> Tuple[int, int]:
    """
    Ingest output from scrapers into the pipeline.

    Args:
        source: Source identifier (producthunt, taaft, etc.)
        items: List of normalized items from scraper
        batch_id: Optional batch ID for idempotency

    Returns:
        Tuple of (items_added, items_skipped)
    """
    if not batch_id:
        batch_id = f"{source}_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

    added = 0
    skipped = 0

    for item in items:
        result = ScrapedItem.create_from_scraper_output(source, item, batch_id)
        if result:
            added += 1
        else:
            skipped += 1

    logger.info(f"Ingested {added} items from {source}, skipped {skipped} duplicates")
    return added, skipped
