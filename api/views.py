from django.conf import settings
from django.db import IntegrityError
from django.db.models import F, Q
from django.http import JsonResponse
from openai import OpenAI
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .models import Category, Deal, News, Review, Tool, ToolSubmission
from .serializers import (
    CategorySerializer,
    DealSerializer,
    NewsDetailSerializer,
    NewsletterSubscriptionSerializer,
    NewsListSerializer,
    ReviewSerializer,
    ToolDetailSerializer,
    ToolListSerializer,
    ToolSubmissionSerializer,
)

# Initialize OpenAI client with new API syntax (openai>=1.0.0)
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


class CustomPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        page_size = super().get_page_size(request)
        req_size = request.query_params.get("page_size")
        print(f"DEBUG: Requested page_size: {req_size}, Final: {page_size}")
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
            queryset = queryset.filter(categories__slug=category)
        if pricing:
            queryset = queryset.filter(pricing_models__contains=[pricing])
        if pricing_type:
            queryset = queryset.filter(pricing_type=pricing_type)
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
        print(f"DEBUG: Search query: {query}")
        if not query:
            return Response([])

        try:
            response = openai_client.embeddings.create(
                model="text-embedding-ada-002", input=query
            )
            embedding = response.data[0].embedding
            print(f"DEBUG: Generated embedding length: {len(embedding)}")

            from django.db import connection

            with connection.cursor() as cursor:
                # First check if we have any tools with embeddings
                cursor.execute(
                    "SELECT COUNT(*) FROM tools WHERE embedding IS NOT NULL "
                    "AND is_active = TRUE"
                )
                count = cursor.fetchone()[0]
                print(f"DEBUG: Tools with embeddings: {count}")

                if count == 0:
                    print("DEBUG: No embeddings found, falling back to text search")
                    raise Exception("No embeddings available")

                cursor.execute(
                    """
                    SELECT t.id, t.name, t.short_description, t.description,
                           t.website, t.logo_url, t.slug,
                           1 - (t.embedding <=> %s::vector) AS similarity
                    FROM tools t
                    WHERE t.is_active = TRUE
                      AND t.embedding IS NOT NULL
                      AND 1 - (t.embedding <=> %s::vector) > 0.3
                    ORDER BY t.embedding <=> %s::vector
                    LIMIT 20
                """,
                    [embedding, embedding, embedding],
                )

                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                print(f"DEBUG: Vector search results: {len(results)}")

            return Response(results)
        except Exception as e:
            print(f"DEBUG: Vector search failed: {e}")
            # Fallback to text search
            tools = Tool.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                is_active=True,
            )[:20]
            print(f"DEBUG: Text search fallback results: {tools.count()}")
            return Response(ToolListSerializer(tools, many=True).data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Review.objects.all()
        tool_id = self.request.query_params.get("tool_id")
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)
        return queryset.order_by("-created_at")


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
def subscribe_newsletter(request):
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

    def get_queryset(self):
        queryset = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "message": "API is running"})


@api_view(["POST"])
@permission_classes([AllowAny])
def search_tools(request):
    query = request.data.get("query", "")
    print(f"DEBUG: Standalone search query: {query}")
    if not query:
        return Response([])

    try:
        response = openai_client.embeddings.create(
            model="text-embedding-ada-002", input=query
        )
        embedding = response.data[0].embedding
        print(f"DEBUG: Generated embedding length: {len(embedding)}")

        from django.db import connection

        with connection.cursor() as cursor:
            # Check if we have any tools with embeddings
            cursor.execute(
                "SELECT COUNT(*) FROM tools WHERE embedding IS NOT NULL "
                "AND is_active = TRUE"
            )
            count = cursor.fetchone()[0]
            print(f"DEBUG: Tools with embeddings: {count}")

            if count == 0:
                print("DEBUG: No embeddings found, falling back to text search")
                raise Exception("No embeddings available")

            cursor.execute(
                """
                SELECT t.id, t.name, t.short_description, t.description,
                       t.website, t.logo_url, t.slug,
                       1 - (t.embedding <=> %s::vector) AS similarity
                FROM tools t
                WHERE t.is_active = TRUE
                  AND t.embedding IS NOT NULL
                  AND 1 - (t.embedding <=> %s::vector) > 0.3
                ORDER BY t.embedding <=> %s::vector
                LIMIT 20
            """,
                [embedding, embedding, embedding],
            )

            columns = [col[0] for col in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            print(f"DEBUG: Vector search results: {len(results)}")

        return Response(results)
    except Exception as e:
        print(f"DEBUG: Vector search failed: {e}")
        # Fallback to text search
        tools = Tool.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True,
        )[:20]
        print(f"DEBUG: Text search fallback results: {tools.count()}")
        return Response(ToolListSerializer(tools, many=True).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def add_tool(request):
    serializer = ToolDetailSerializer(data=request.data)
    if serializer.is_valid():
        tool = serializer.save()
        return Response(ToolDetailSerializer(tool).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
