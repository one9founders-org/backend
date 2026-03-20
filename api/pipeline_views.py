"""
API Views for the AI News Pipeline.
Provides endpoints for pipeline management, monitoring, and manual overrides.
"""

import logging
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .pipeline_engine import PipelineOrchestrator, ingest_scraper_output
from .pipeline_models import (
    NewsDraft,
    PipelineConfig,
    PipelineRun,
    PublishedArticle,
    QualifiedNewsItem,
    ScrapedItem,
)
from .pipeline_serializers import (
    NewsDraftSerializer,
    PipelineConfigSerializer,
    PipelineRunSerializer,
    PublishedArticleSerializer,
    QualifiedNewsItemSerializer,
    ScrapedItemSerializer,
)

logger = logging.getLogger(__name__)


class ScrapedItemViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing scraped items."""

    queryset = ScrapedItem.objects.all()
    serializer_class = ScrapedItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        source = self.request.query_params.get("source")
        status_filter = self.request.query_params.get("status")
        days = self.request.query_params.get("days")

        if source:
            queryset = queryset.filter(source=source)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if days:
            cutoff = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(scraped_at__gte=cutoff)

        return queryset


class QualifiedNewsItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing qualified news items."""

    queryset = QualifiedNewsItem.objects.all().select_related("scraped_item")
    serializer_class = QualifiedNewsItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        status_filter = self.request.query_params.get("status")
        min_score = self.request.query_params.get("min_score")
        max_score = self.request.query_params.get("max_score")

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if min_score:
            queryset = queryset.filter(relevance_score__gte=int(min_score))
        if max_score:
            queryset = queryset.filter(relevance_score__lte=int(max_score))

        return queryset

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Manually approve a queued item."""
        item = self.get_object()
        item.status = "manually_approved"
        item.reviewed_by = (
            request.user.username if request.user.is_authenticated else "anonymous"
        )
        item.reviewed_at = timezone.now()
        item.save()
        return Response({"status": "approved", "id": item.id})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Manually reject an item."""
        item = self.get_object()
        item.status = "manually_rejected"
        item.status_reason = request.data.get("reason", "")
        item.reviewed_by = (
            request.user.username if request.user.is_authenticated else "anonymous"
        )
        item.reviewed_at = timezone.now()
        item.save()
        return Response({"status": "rejected", "id": item.id})


class NewsDraftViewSet(viewsets.ModelViewSet):
    """ViewSet for managing news drafts."""

    queryset = NewsDraft.objects.all().select_related("qualified_item__scraped_item")
    serializer_class = NewsDraftSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Manually publish a draft."""
        draft = self.get_object()

        if not PipelineConfig.is_publishing_enabled():
            return Response(
                {"error": "Publishing is disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )

        orchestrator = PipelineOrchestrator()
        slot, _ = orchestrator.engine.get_next_publish_slot()
        result = orchestrator.engine.publish_draft(draft, slot)

        if result:
            return Response({"status": "published", "news_id": result.news.id})
        return Response(
            {"error": "Publishing failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        """Regenerate content for a draft."""
        draft = self.get_object()
        orchestrator = PipelineOrchestrator()

        new_draft = orchestrator.engine.generate_content(draft.qualified_item)
        if new_draft:
            draft.delete()
            return Response(NewsDraftSerializer(new_draft).data)
        return Response(
            {"error": "Regeneration failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class PublishedArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing published articles."""

    queryset = PublishedArticle.objects.all().select_related("news", "draft")
    serializer_class = PublishedArticleSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        source = self.request.query_params.get("source")
        days = self.request.query_params.get("days")

        if source:
            queryset = queryset.filter(source=source)
        if days:
            cutoff = timezone.now() - timedelta(days=int(days))
            queryset = queryset.filter(published_at__gte=cutoff)

        return queryset


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing pipeline runs."""

    queryset = PipelineRun.objects.all()
    serializer_class = PipelineRunSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()

        run_type = self.request.query_params.get("type")
        status_filter = self.request.query_params.get("status")

        if run_type:
            queryset = queryset.filter(run_type=run_type)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset


@api_view(["POST"])
@permission_classes([AllowAny])
def ingest_scraped_data(request):
    """
    Ingest scraped data from external scrapers.

    Expected payload:
    {
        "source": "producthunt|taaft|futurepedia|huggingface",
        "items": [...],
        "batch_id": "optional_batch_id"
    }
    """
    source = request.data.get("source")
    items = request.data.get("items", [])
    batch_id = request.data.get("batch_id")

    if not source:
        return Response(
            {"error": "source is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not items:
        return Response(
            {"error": "items is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_sources = ["producthunt", "taaft", "futurepedia", "huggingface", "rss_news", "manual"]
    if source not in valid_sources:
        return Response(
            {"error": f"Invalid source. Must be one of: {valid_sources}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    added, skipped = ingest_scraper_output(source, items, batch_id)

    return Response(
        {
            "status": "success",
            "source": source,
            "items_added": added,
            "items_skipped": skipped,
            "batch_id": batch_id,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def run_pipeline(request):
    """
    Trigger pipeline execution.

    Expected payload:
    {
        "type": "score|generate|publish|full",
        "source": "optional_source_filter",
        "limit": 50
    }
    """
    run_type = request.data.get("type", "full")
    source = request.data.get("source")
    limit = request.data.get("limit", 50)

    orchestrator = PipelineOrchestrator()

    if run_type == "score":
        run = orchestrator.run_scoring(source, limit)
    elif run_type == "generate":
        run = orchestrator.run_content_generation(limit)
    elif run_type == "publish":
        run = orchestrator.run_publishing(limit)
    elif run_type == "full":
        run = orchestrator.run_full_pipeline(source, limit, limit // 5, 5)
    else:
        return Response(
            {"error": "Invalid type. Must be: score, generate, publish, or full"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(PipelineRunSerializer(run).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def pipeline_stats(request):
    """Get pipeline statistics and status."""
    today = timezone.now().date()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    scraped_stats = ScrapedItem.objects.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(scraped_at__gte=today_start)),
        pending=Count("id", filter=Q(status="scraped")),
    )

    qualified_stats = QualifiedNewsItem.objects.aggregate(
        total=Count("id"),
        auto_approved=Count("id", filter=Q(status="auto_approved")),
        queued=Count("id", filter=Q(status="queued")),
        auto_rejected=Count("id", filter=Q(status="auto_rejected")),
    )

    draft_stats = NewsDraft.objects.aggregate(
        total=Count("id"),
        ready=Count("id", filter=Q(status__in=["generated", "ready"])),
        published=Count("id", filter=Q(status="published")),
    )

    published_stats = PublishedArticle.objects.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(published_at__gte=today_start)),
        this_week=Count("id", filter=Q(published_at__date__gte=week_ago)),
    )

    by_source = (
        ScrapedItem.objects.values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    recent_runs = PipelineRun.objects.order_by("-started_at")[:5]

    return Response(
        {
            "scraped": scraped_stats,
            "qualified": qualified_stats,
            "drafts": draft_stats,
            "published": published_stats,
            "by_source": list(by_source),
            "recent_runs": PipelineRunSerializer(recent_runs, many=True).data,
            "config": {
                "publishing_enabled": PipelineConfig.is_publishing_enabled(),
                "max_articles_per_day": PipelineConfig.get_max_articles_per_day(),
                "score_thresholds": PipelineConfig.get_score_thresholds(),
            },
        }
    )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def pipeline_config(request):
    """Get or update pipeline configuration."""
    if request.method == "GET":
        configs = PipelineConfig.objects.all()
        return Response(PipelineConfigSerializer(configs, many=True).data)

    key = request.data.get("key")
    value = request.data.get("value")

    if not key:
        return Response(
            {"error": "key is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    config = PipelineConfig.set(
        key=key,
        value=value,
        description=request.data.get("description", ""),
        updated_by=request.user.username if request.user.is_authenticated else "api",
    )

    return Response(PipelineConfigSerializer(config).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def toggle_publishing(request):
    """Toggle the publishing kill-switch."""
    enabled = request.data.get("enabled", True)

    PipelineConfig.set(
        key="publishing_enabled",
        value=enabled,
        description="Kill-switch for auto-publishing",
        updated_by=request.user.username if request.user.is_authenticated else "api",
    )

    return Response(
        {
            "publishing_enabled": enabled,
            "message": f"Publishing {'enabled' if enabled else 'disabled'}",
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def news_feed(request):
    """
    Get published news for the frontend.
    Supports filtering by date range and highlights.
    """
    from .models import News
    from .serializers import NewsListSerializer

    period = request.query_params.get("period", "week")
    highlights = request.query_params.get("highlights", "false").lower() == "true"

    today = timezone.now().date()

    if period == "today":
        start_date = today
    elif period == "yesterday":
        start_date = today - timedelta(days=1)
        end_date = today
    elif period == "week":
        start_date = today - timedelta(days=7)
    else:
        start_date = today - timedelta(days=30)

    queryset = News.objects.filter(
        is_published=True,
        published_at__date__gte=start_date,
    ).order_by("-published_at")

    if highlights:
        article_ids = PublishedArticle.objects.filter(
            relevance_score__gte=70
        ).values_list("news_id", flat=True)
        queryset = queryset.filter(id__in=article_ids)

    if period == "yesterday":
        queryset = queryset.filter(published_at__date__lt=end_date)

    return Response(
        {
            "period": period,
            "count": queryset.count(),
            "items": NewsListSerializer(queryset[:50], many=True).data,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def run_scraper(request):
    """
    Run a scraper and ingest the results.
    This endpoint is designed to be called by n8n workflows.

    Expected payload:
    {
        "source": "producthunt|taaft|futurepedia|huggingface",
        "limit": 50,
        "days_back": 1
    }

    Returns:
    {
        "status": "success|failed",
        "source": "...",
        "items_scraped": N,
        "items_added": N,
        "items_skipped": N,
        "batch_id": "...",
        "error": "..." (if failed)
    }
    """
    import uuid

    source = request.data.get("source")
    limit = int(request.data.get("limit", 50))
    days_back = float(request.data.get("days_back", 1))

    valid_sources = ["producthunt", "taaft", "futurepedia", "huggingface", "rss_news"]
    if not source or source not in valid_sources:
        return Response(
            {"error": f"Invalid source. Must be one of: {valid_sources}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    batch_id = (
        f"{source}_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )

    run = PipelineRun.objects.create(
        run_type="scrape",
        source=source,
        batch_id=batch_id,
        status="running",
    )

    try:
        items = []

        if source == "producthunt":
            from scrapers.producthunt.scraper import ProductHuntScraper

            scraper = ProductHuntScraper(
                headless=True, days_back=int(days_back), limit=limit
            )
            items = scraper.scrape()

        elif source == "huggingface":
            from scrapers.huggingface.scraper import HuggingFaceScraper

            scraper = HuggingFaceScraper(days_back=int(days_back), limit=limit)
            items = scraper.scrape()

        elif source == "taaft":
            from scrapers.taaft.scraper import TAAFTScraper

            scraper = TAAFTScraper(headless=True, limit=limit)
            items = scraper.scrape()

        elif source == "futurepedia":
            from scrapers.futurepedia.scraper import FuturepediaScraper

            scraper = FuturepediaScraper(headless=True, limit_per_category=limit)
            items = scraper.scrape()

        elif source == "rss_news":
            from scrapers.rss_news.scraper import RSSNewsScraper

            scraper = RSSNewsScraper(limit_per_source=limit)
            items = scraper.scrape()

        added, skipped = ingest_scraper_output(source, items, batch_id)

        run.items_processed = len(items)
        run.items_succeeded = added
        run.items_failed = skipped
        run.complete(success=True)

        logger.info(
            f"Scraper {source} completed: {len(items)} scraped, "
            f"{added} added, {skipped} skipped"
        )

        return Response(
            {
                "status": "success",
                "source": source,
                "items_scraped": len(items),
                "items_added": added,
                "items_skipped": skipped,
                "batch_id": batch_id,
            }
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Scraper {source} failed: {error_msg}", exc_info=True)

        run.complete(success=False, error=error_msg)

        return Response(
            {
                "status": "failed",
                "source": source,
                "error": error_msg,
                "batch_id": batch_id,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
