import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.utils import timezone
from openai import OpenAI
from rest_framework import status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import (
    Category,
    Deal,
    Guide,
    Lab,
    News,
    NewsUpvote,
    Review,
    SearchQuery,
    Tool,
    ToolClick,
    ToolSubmission,
    ToolUsage,
    Workshop,
)
from .serializers import (
    CategorySerializer,
    DealSerializer,
    GuideDetailSerializer,
    GuideListSerializer,
    LabDetailSerializer,
    LabListSerializer,
    NewsDetailSerializer,
    NewsletterSubscriptionSerializer,
    NewsListSerializer,
    ReviewSerializer,
    ToolDetailSerializer,
    ToolListSerializer,
    ToolSubmissionSerializer,
    TrendingToolSerializer,
    WorkshopDetailSerializer,
    WorkshopListSerializer,
)

logger = logging.getLogger(__name__)

# Initialize OpenAI client with new API syntax (openai>=1.0.0)
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        page_size = super().get_page_size(request)
        req_size = request.query_params.get("page_size")
        logger.debug("Requested page_size: %s, Final: %s", req_size, page_size)
        return page_size

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response["X-Page-Size-Used"] = str(self.page_size)
        return response


class ToolViewSet(viewsets.ModelViewSet):
    queryset = Tool.objects.filter(is_active=True).prefetch_related("categories")
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ToolDetailSerializer
        return ToolListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        pricing = self.request.query_params.get("pricing")
        pricing_type = self.request.query_params.get("pricing_type")
        featured = self.request.query_params.get("featured")
        startup_friendly = self.request.query_params.get("startup_friendly")

        if category:
            # Support both category name and slug for filtering
            queryset = queryset.filter(
                Q(categories__slug=category.lower())
                | Q(categories__name__iexact=category)
            )
        if pricing:
            queryset = queryset.filter(pricing_models__contains=[pricing])
        if pricing_type:
            pricing_types = [pt.strip().lower() for pt in pricing_type.split(",")]
            queryset = queryset.filter(pricing_type__in=pricing_types)
        if featured:
            queryset = queryset.filter(is_featured=True)
        if startup_friendly:
            queryset = queryset.filter(startup_friendly=True)

        return queryset.distinct()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Tool.objects.filter(pk=instance.pk).update(views_count=F("views_count") + 1)
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def search(self, request):
        query = request.data.get("query", "")
        logger.debug("Search query: %s", query)
        if not query:
            return Response([])

        try:
            from .faiss_search import FAISSSearchService

            service = FAISSSearchService.get_instance()
            results = service.search(query, top_k=20, similarity_threshold=0.3)
            if results is not None:
                logger.debug("FAISS search results: %d", len(results))
                return Response(results)
            logger.debug("FAISS index not available, falling back to text search")
            raise Exception("FAISS index not available")
        except Exception as e:
            logger.warning("FAISS search failed: %s", e)
            tools = Tool.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                is_active=True,
            )[:20]
            logger.debug("Text search fallback results: %d", tools.count())
            return Response(ToolListSerializer(tools, many=True).data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        queryset = Review.objects.all()
        tool_id = self.request.query_params.get("tool_id")
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        from .recaptcha import verify_recaptcha

        recaptcha_token = request.data.get("recaptcha_token")
        if recaptcha_token:
            result = verify_recaptcha(recaptcha_token, action="write_review")
            if not result["success"]:
                return Response(
                    {"error": result["error"], "recaptcha_failed": True},
                    status=status.HTTP_403_FORBIDDEN,
                )

        return super().create(request, *args, **kwargs)


class DealViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Deal.objects.filter(is_active=True).order_by(
        "-featured_deal", "-created_at"
    )
    serializer_class = DealSerializer
    permission_classes = [AllowAny]


class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        News.objects.filter(is_published=True)
        .prefetch_related("related_tools")
        .order_by("-published_at")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return NewsDetailSerializer
        return NewsListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        News.objects.filter(pk=instance.pk).update(views_count=F("views_count") + 1)
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def subscribe_newsletter(request):
    from .recaptcha import verify_recaptcha

    recaptcha_token = request.data.get("recaptcha_token")
    if recaptcha_token:
        result = verify_recaptcha(recaptcha_token, action="newsletter_subscribe")
        if not result["success"]:
            return Response(
                {"error": result["error"], "recaptcha_failed": True},
                status=status.HTTP_403_FORBIDDEN,
            )

    serializer = NewsletterSubscriptionSerializer(data=request.data)
    if serializer.is_valid():
        try:
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            if "unique" in str(e).lower():
                return Response(
                    {"error": "Email already subscribed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ToolSubmissionViewSet(viewsets.ModelViewSet):
    queryset = ToolSubmission.objects.all().order_by("-created_at")
    serializer_class = ToolSubmissionSerializer
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request, *args, **kwargs):
        from .recaptcha import verify_recaptcha

        recaptcha_token = request.data.get("recaptcha_token")
        if recaptcha_token:
            result = verify_recaptcha(recaptcha_token, action="submit_tool")
            if not result["success"]:
                return Response(
                    {"error": result["error"], "recaptcha_failed": True},
                    status=status.HTTP_403_FORBIDDEN,
                )

        return super().create(request, *args, **kwargs)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "message": "API is running"})


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def search_tools(request):
    query = request.data.get("query", "")
    logger.debug("Standalone search query: %s", query)
    if not query:
        return Response([])

    try:
        from .faiss_search import FAISSSearchService

        service = FAISSSearchService.get_instance()
        results = service.search(query, top_k=20, similarity_threshold=0.3)
        if results is not None:
            logger.debug("FAISS search results: %d", len(results))
            return Response(results)
        logger.debug("FAISS index not available, falling back to text search")
        raise Exception("FAISS index not available")
    except Exception as e:
        logger.warning("FAISS search failed: %s", e)
        tools = Tool.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True,
        )[:20]
        logger.debug("Text search fallback results: %d", tools.count())
        return Response(ToolListSerializer(tools, many=True).data)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def add_tool(request):
    serializer = ToolDetailSerializer(data=request.data)
    if serializer.is_valid():
        tool = serializer.save()
        return Response(ToolDetailSerializer(tool).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def smart_search(request):
    """AI-powered smart search with intent parsing,
    hybrid filtering, and task decomposition."""
    query = request.data.get("query", "").strip()
    if not query:
        return Response(
            {"error": "query is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(query) > 500:
        return Response(
            {"error": "Query too long (max 500 characters)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from .smart_search import smart_search_orchestrator

        top_k = min(int(request.data.get("top_k", 20)), 50)
        result = smart_search_orchestrator(query, top_k=top_k)
        return Response(result)
    except Exception as e:
        logger.error("Smart search failed for '%s': %s", query, e, exc_info=True)
        # Graceful fallback to basic FAISS search
        try:
            from .faiss_search import FAISSSearchService

            service = FAISSSearchService.get_instance()
            results = service.search(query, top_k=20, similarity_threshold=0.3)
            if results is not None:
                return Response(
                    {
                        "mode": "search",
                        "parsed_intent": {
                            "semantic_query": query,
                            "filters": {},
                            "explanation": "Fallback to basic semantic search",
                        },
                        "results": results,
                        "total_results": len(results),
                        "suggestions": [],
                    }
                )
        except Exception:
            pass

        # Last resort: text search
        tools = Tool.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True,
        )[:20]
        return Response(
            {
                "mode": "search",
                "parsed_intent": {
                    "semantic_query": query,
                    "filters": {},
                    "explanation": "Basic text search fallback",
                },
                "results": ToolListSerializer(tools, many=True).data,
                "total_results": tools.count(),
                "suggestions": ["Try a more specific search query"],
            }
        )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def sync_lacreme(request):
    from .lacreme_scraper import run

    scraped_tools = run()

    # Existing tool names (case-insensitive safe compare)
    existing_names = set(Tool.objects.values_list("name", flat=True))

    added = 0
    skipped = 0

    for t in scraped_tools:
        name = t.get("name")

        if not name:
            skipped += 1
            continue

        if name in existing_names:
            skipped += 1
            continue

        try:
            Tool.objects.create(
                name=name,
                short_description=t.get("short_description", ""),
                logo_url=t.get("logo_url", ""),
                website=t.get("website", ""),
                rating=0,
                review_count=0,
                verified=False,
            )
            added += 1
            existing_names.add(name)

        except IntegrityError:
            skipped += 1

    return JsonResponse(
        {
            "status": "success",
            "scraped": len(scraped_tools),
            "added": added,
            "skipped": skipped,
        }
    )


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def track_tool_usage(request):
    tool_id = request.data.get("tool_id")
    session_id = request.data.get("session_id", "")

    if not tool_id:
        return Response(
            {"error": "tool_id is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        tool = Tool.objects.get(id=tool_id, is_active=True)
    except Tool.DoesNotExist:
        return Response({"error": "Tool not found"}, status=status.HTTP_404_NOT_FOUND)

    user = request.user if request.user.is_authenticated else None
    ip_address = get_client_ip(request)

    usage = ToolUsage.objects.create(
        tool=tool,
        user=user,
        session_id=session_id,
        ip_address=ip_address,
    )

    return Response(
        {"message": "Usage tracked", "id": usage.id}, status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def track_tool_click(request):
    tool_id = request.data.get("tool_id")
    action = request.data.get("action")
    session_id = request.data.get("session_id", "")
    referrer = request.data.get("referrer", "")

    if not tool_id or not action:
        return Response(
            {"error": "tool_id and action are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_actions = [choice[0] for choice in ToolClick.ACTION_CHOICES]
    if action not in valid_actions:
        return Response(
            {"error": f"Invalid action. Must be one of: {valid_actions}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        tool = Tool.objects.get(id=tool_id, is_active=True)
    except Tool.DoesNotExist:
        return Response({"error": "Tool not found"}, status=status.HTTP_404_NOT_FOUND)

    user = request.user if request.user.is_authenticated else None
    ip_address = get_client_ip(request)

    click = ToolClick.objects.create(
        tool=tool,
        action=action,
        user=user,
        session_id=session_id,
        ip_address=ip_address,
        referrer=referrer,
    )

    return Response(
        {"message": "Click tracked", "id": click.id}, status=status.HTTP_201_CREATED
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def track_search_query(request):
    query = request.data.get("query", "")
    session_id = request.data.get("session_id", "")
    results_count = request.data.get("results_count", 0)
    filters = request.data.get("filters", {})

    if not query:
        return Response(
            {"error": "query is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user if request.user.is_authenticated else None
    ip_address = get_client_ip(request)

    search = SearchQuery.objects.create(
        query=query,
        user=user,
        session_id=session_id,
        ip_address=ip_address,
        results_count=results_count,
        filters=filters,
    )

    return Response(
        {"message": "Search tracked", "id": search.id}, status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def trending_tools(request):
    days = int(request.query_params.get("days", 7))
    limit = int(request.query_params.get("limit", 10))

    since = timezone.now() - timedelta(days=days)

    tools = (
        Tool.objects.filter(is_active=True)
        .annotate(
            usage_count=Count(
                "usages", filter=Q(usages__created_at__gte=since), distinct=True
            ),
            click_count=Count(
                "clicks", filter=Q(clicks__created_at__gte=since), distinct=True
            ),
        )
        .order_by("-usage_count", "-click_count", "-views_count")[:limit]
    )

    serializer = TrendingToolSerializer(tools, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def tool_usage_count(request, tool_id):
    try:
        tool = Tool.objects.get(id=tool_id, is_active=True)
    except Tool.DoesNotExist:
        return Response({"error": "Tool not found"}, status=status.HTTP_404_NOT_FOUND)

    usage_count = ToolUsage.objects.filter(tool=tool).count()

    return Response(
        {
            "tool_id": tool_id,
            "tool_name": tool.name,
            "usage_count": usage_count,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def upvote_news(request, news_id):
    """Upvote a news article. Supports authenticated users and anonymous sessions."""
    try:
        news = News.objects.get(id=news_id, is_published=True)
    except News.DoesNotExist:
        return Response({"error": "News not found"}, status=status.HTTP_404_NOT_FOUND)

    user = request.user if request.user.is_authenticated else None
    session_id = request.headers.get("X-Session-ID", "") or request.data.get(
        "session_id", ""
    )
    ip_address = get_client_ip(request)

    if not user and not session_id:
        return Response(
            {"error": "Either login or provide X-Session-ID header"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        if user:
            upvote, created = NewsUpvote.objects.get_or_create(
                news=news,
                user=user,
                defaults={"ip_address": ip_address},
            )
        else:
            upvote, created = NewsUpvote.objects.get_or_create(
                news=news,
                session_id=session_id,
                defaults={"ip_address": ip_address},
            )

        if created:
            News.objects.filter(pk=news.pk).update(upvote_count=F("upvote_count") + 1)
            news.refresh_from_db()
            return Response(
                {
                    "message": "Upvoted successfully",
                    "upvote_count": news.upvote_count,
                    "has_upvoted": True,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            return Response(
                {
                    "message": "Already upvoted",
                    "upvote_count": news.upvote_count,
                    "has_upvoted": True,
                },
                status=status.HTTP_200_OK,
            )
    except IntegrityError:
        return Response(
            {"error": "Already upvoted", "has_upvoted": True},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["DELETE"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def remove_upvote_news(request, news_id):
    """Remove upvote from a news article."""
    try:
        news = News.objects.get(id=news_id, is_published=True)
    except News.DoesNotExist:
        return Response({"error": "News not found"}, status=status.HTTP_404_NOT_FOUND)

    user = request.user if request.user.is_authenticated else None
    session_id = request.headers.get("X-Session-ID", "") or request.data.get(
        "session_id", ""
    )

    if not user and not session_id:
        return Response(
            {"error": "Either login or provide X-Session-ID header"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if user:
        deleted, _ = NewsUpvote.objects.filter(news=news, user=user).delete()
    else:
        deleted, _ = NewsUpvote.objects.filter(
            news=news, session_id=session_id
        ).delete()

    if deleted:
        News.objects.filter(pk=news.pk).update(upvote_count=F("upvote_count") - 1)
        news.refresh_from_db()
        return Response(
            {
                "message": "Upvote removed",
                "upvote_count": max(0, news.upvote_count),
                "has_upvoted": False,
            }
        )
    else:
        return Response(
            {
                "message": "No upvote to remove",
                "upvote_count": news.upvote_count,
                "has_upvoted": False,
            }
        )


# --- Learning Content ViewSets ---


class LearningContentViewSetMixin:
    """Shared filtering logic for Guide, Lab, and Workshop viewsets."""

    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        difficulty = self.request.query_params.get("difficulty")
        category = self.request.query_params.get("category")
        audience = self.request.query_params.get("audience")
        pricing = self.request.query_params.get("pricing")
        featured = self.request.query_params.get("featured")
        tool = self.request.query_params.get("tool")

        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if category:
            queryset = queryset.filter(category=category)
        if audience:
            queryset = queryset.filter(audience=audience)
        if pricing:
            queryset = queryset.filter(pricing=pricing)
        if featured:
            queryset = queryset.filter(is_featured=True)
        if tool:
            queryset = queryset.filter(
                Q(tools_used__slug=tool) | Q(tools_used__name__iexact=tool)
            ).distinct()

        return queryset

    @action(detail=False, methods=["get"])
    def filters(self, request):
        """Return available filter options for the content type."""
        from .models import LearningContent

        return Response(
            {
                "difficulty": [
                    {"value": k, "label": v}
                    for k, v in LearningContent.DIFFICULTY_CHOICES
                ],
                "category": [
                    {"value": k, "label": v}
                    for k, v in LearningContent.CATEGORY_CHOICES
                ],
                "audience": [
                    {"value": k, "label": v}
                    for k, v in LearningContent.AUDIENCE_CHOICES
                ],
                "pricing": [
                    {"value": k, "label": v} for k, v in LearningContent.PRICING_CHOICES
                ],
            }
        )


class GuideViewSet(LearningContentViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Guide.objects.filter(is_published=True).prefetch_related("tools_used")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GuideDetailSerializer
        return GuideListSerializer


class LabViewSet(LearningContentViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Lab.objects.filter(is_published=True).prefetch_related("tools_used")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LabDetailSerializer
        return LabListSerializer


class WorkshopViewSet(LearningContentViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Workshop.objects.filter(is_published=True).prefetch_related("tools_used")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return WorkshopDetailSerializer
        return WorkshopListSerializer
