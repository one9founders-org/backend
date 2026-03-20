from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AgentCategory, AIAgent
from .serializers import (
    AgentCategorySerializer,
    AgentDetailSerializer,
    AgentListSerializer,
)

ACCESS_PARAM_MAP = {
    "open-source": "Open Source",
    "closed-source": "Closed Source",
    "api": "API",
}

SORT_MAP = {
    "popular": "-popularity_score",
    "trending": "-views_7d",
    "newest": "-created_at",
    "top-rated": "-average_rating",
    "most-upvoted": "-upvotes",
}


class AgentPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100


class AgentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = AgentPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AgentDetailSerializer
        return AgentListSerializer

    def get_queryset(self):
        queryset = AIAgent.objects.select_related("category").all()

        # Filter by category slug
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)

        # Filter by pricing model (case-insensitive)
        pricing = self.request.query_params.get("pricing")
        if pricing:
            queryset = queryset.filter(pricing_model__iexact=pricing)

        # Filter by access type (map hyphenated params to model values)
        access = self.request.query_params.get("access")
        if access:
            model_value = ACCESS_PARAM_MAP.get(access.lower(), access)
            queryset = queryset.filter(access=model_value)

        # Full-text search on name + short_description
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(short_description__icontains=search)
            )

        # Sort
        sort = self.request.query_params.get("sort", "popular")
        order_field = SORT_MAP.get(sort, "-popularity_score")
        queryset = queryset.order_by(order_field)

        return queryset


class AgentCategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        categories = AgentCategory.objects.prefetch_related("agents").order_by(
            "-agent_count"
        )
        serializer = AgentCategorySerializer(categories, many=True)
        return Response({"categories": serializer.data})


class AgentStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        total_agents = AIAgent.objects.count()
        total_categories = AgentCategory.objects.count()
        free_agents = AIAgent.objects.filter(pricing_model="Free").count()
        open_source_agents = AIAgent.objects.filter(access="Open Source").count()
        featured_agents = AIAgent.objects.filter(is_featured=True).count()

        pricing_breakdown = {}
        for row in (
            AIAgent.objects.values("pricing_model")
            .annotate(count=Count("id"))
            .order_by("-count")
        ):
            if row["pricing_model"]:
                pricing_breakdown[row["pricing_model"]] = row["count"]

        access_breakdown = {}
        for row in (
            AIAgent.objects.values("access")
            .annotate(count=Count("id"))
            .order_by("-count")
        ):
            if row["access"]:
                access_breakdown[row["access"]] = row["count"]

        return Response(
            {
                "total_agents": total_agents,
                "total_categories": total_categories,
                "free_agents": free_agents,
                "open_source_agents": open_source_agents,
                "featured_agents": featured_agents,
                "pricing_breakdown": pricing_breakdown,
                "access_breakdown": access_breakdown,
            }
        )
