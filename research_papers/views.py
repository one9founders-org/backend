import logging
from datetime import timedelta

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Paper
from .serializers import PaperDetailSerializer, PaperListSerializer

logger = logging.getLogger(__name__)

# Tag-to-category mapping for tab filtering
TAG_CATEGORY_MAP = {
    "llms": ["LLMs", "GPT", "language model", "transformer", "fine-tuning"],
    "agents": ["agents", "autonomous", "planning", "tool use"],
    "rag": ["RAG", "retrieval", "retrieval-augmented", "vector"],
    "vision": ["vision", "image", "visual", "object detection", "segmentation"],
    "multimodal": ["multimodal", "VLM", "vision-language", "audio-visual"],
    "rl": [
        "reinforcement learning",
        "RLHF",
        "reward model",
        "policy",
    ],
}


class PaperPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PaperViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "arxiv_id"
    lookup_value_regex = r"[\d.]+"
    pagination_class = PaperPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PaperDetailSerializer
        return PaperListSerializer

    def get_queryset(self):
        queryset = Paper.objects.all()

        # Tab filter (maps to ai_tags)
        tab = self.request.query_params.get("tab")
        if tab and tab != "all" and tab in TAG_CATEGORY_MAP:
            tag_keywords = TAG_CATEGORY_MAP[tab]
            q_filter = Q()
            for keyword in tag_keywords:
                q_filter |= Q(ai_tags__icontains=keyword)
            queryset = queryset.filter(q_filter)

        # Trending filter
        trending = self.request.query_params.get("trending")
        if trending and trending.lower() == "true":
            queryset = queryset.filter(is_trending=True)

        # Has code filter
        has_code = self.request.query_params.get("has_code")
        if has_code and has_code.lower() == "true":
            queryset = queryset.exclude(code_url="")

        # Difficulty filter
        difficulty = self.request.query_params.get("difficulty")
        if difficulty:
            queryset = queryset.filter(ai_difficulty=difficulty)

        # Date range filters
        after = self.request.query_params.get("after")
        if after:
            queryset = queryset.filter(published_at__date__gte=after)

        before = self.request.query_params.get("before")
        if before:
            queryset = queryset.filter(published_at__date__lte=before)

        # Search
        search = self.request.query_params.get("search")
        if search:
            try:
                vector = (
                    SearchVector("title", weight="A")
                    + SearchVector("abstract", weight="B")
                    + SearchVector("ai_summary", weight="C")
                )
                query = SearchQuery(search)
                queryset = (
                    queryset.annotate(rank=SearchRank(vector, query))
                    .filter(
                        Q(rank__gte=0.01)
                        | Q(title__icontains=search)
                        | Q(abstract__icontains=search)
                    )
                    .order_by("-rank")
                )
                return queryset
            except Exception:
                queryset = queryset.filter(
                    Q(title__icontains=search) | Q(abstract__icontains=search)
                )

        # Sort
        sort = self.request.query_params.get("sort", "newest")
        sort_map = {
            "newest": "-published_at",
            "upvotes": "-hf_upvotes",
            "citations": "-citation_count",
        }
        order = sort_map.get(sort, "-published_at")
        queryset = queryset.order_by(order)

        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Related papers (overlapping ai_tags)
        if instance.ai_tags:
            q_filter = Q()
            for tag in instance.ai_tags[:5]:
                q_filter |= Q(ai_tags__icontains=tag)
            related = (
                Paper.objects.filter(q_filter)
                .exclude(arxiv_id=instance.arxiv_id)
                .order_by("-published_at")[:5]
            )
            data["related_papers"] = PaperListSerializer(related, many=True).data
        else:
            data["related_papers"] = []

        return Response(data)


class PaperTrendingView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        seven_days_ago = timezone.now() - timedelta(days=7)
        papers = Paper.objects.filter(
            is_trending=True, published_at__gte=seven_days_ago
        ).order_by("-hf_upvotes")[:10]
        serializer = PaperListSerializer(papers, many=True)
        return Response(serializer.data)


class PaperStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        total_papers = Paper.objects.count()
        papers_today = Paper.objects.filter(created_at__gte=today_start).count()
        papers_this_week = Paper.objects.filter(created_at__gte=week_start).count()

        # Top tags from recent papers
        recent_papers = Paper.objects.filter(
            created_at__gte=week_start, is_enriched=True
        )
        tag_counts = {}
        for paper in recent_papers:
            for tag in paper.ai_tags or []:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:15]
        top_tags = [{"tag": t[0], "count": t[1]} for t in top_tags]

        return Response(
            {
                "total_papers": total_papers,
                "papers_today": papers_today,
                "papers_this_week": papers_this_week,
                "top_tags": top_tags,
            }
        )
