import logging

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RagTool
from .serializers import (
    RagToolCompareSerializer,
    RagToolDetailSerializer,
    RagToolListSerializer,
)

logger = logging.getLogger(__name__)


class RagToolPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200


class RagToolViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = RagToolPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RagToolDetailSerializer
        return RagToolListSerializer

    def get_queryset(self):
        queryset = RagTool.objects.all()

        # Filter by category
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)

        # Filter by pricing (comma-separated)
        pricing = self.request.query_params.get("pricing")
        if pricing:
            pricing_list = [p.strip() for p in pricing.split(",")]
            queryset = queryset.filter(pricing_model__in=pricing_list)

        # Filter by deployment option
        deployment = self.request.query_params.get("deployment")
        if deployment:
            for opt in deployment.split(","):
                queryset = queryset.filter(deployment_options__contains=[opt.strip()])

        # Filter by integration
        integration = self.request.query_params.get("integration")
        if integration:
            queryset = queryset.filter(integrations__contains=[integration])

        # Filter by SDK language
        sdk = self.request.query_params.get("sdk")
        if sdk:
            queryset = queryset.filter(sdk_languages__contains=[sdk])

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Search
        search = self.request.query_params.get("search")
        if search:
            try:
                vector = SearchVector("name", weight="A") + SearchVector(
                    "description", weight="B"
                )
                query = SearchQuery(search)
                queryset = (
                    queryset.annotate(rank=SearchRank(vector, query))
                    .filter(
                        Q(rank__gte=0.01)
                        | Q(name__icontains=search)
                        | Q(description__icontains=search)
                    )
                    .order_by("-rank")
                )
            except Exception:
                queryset = queryset.filter(
                    Q(name__icontains=search) | Q(description__icontains=search)
                )

        # Sort
        sort = self.request.query_params.get("sort", "-overall_rating")
        sort_map = {
            "stars": "-github_stars",
            "-stars": "github_stars",
            "rating": "-overall_rating",
            "-rating": "overall_rating",
            "name": "name",
            "newest": "-created_at",
        }
        order = sort_map.get(sort, sort)
        if not search:
            queryset = queryset.order_by(order)

        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        # Include similar tools
        similar = RagTool.objects.filter(
            category=instance.category, status="active"
        ).exclude(id=instance.id)[:5]
        data["similar_tools"] = RagToolListSerializer(similar, many=True).data

        return Response(data)


class RagCategoriesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        counts = (
            RagTool.objects.filter(status="active")
            .values("category")
            .annotate(count=Count("id"))
        )
        result = {item["category"]: item["count"] for item in counts}
        return Response(result)


class RagCompareView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        slugs = request.query_params.get("slugs", "")
        if not slugs:
            return Response(
                {"error": "slugs parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slug_list = [s.strip() for s in slugs.split(",")][:4]
        tools = RagTool.objects.filter(slug__in=slug_list, status="active")
        serializer = RagToolCompareSerializer(tools, many=True)
        return Response(serializer.data)
