import logging

from django.db.models import F
from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import (
    AudienceType,
    Course,
    CourseCategory,
    EducationGuide,
    EducationWorkshop,
    LandingPage,
    LearningPath,
)
from .serializers import (
    AudienceTypeSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseInquiryCreateSerializer,
    CourseListSerializer,
    GuideDetailSerializer,
    GuideListSerializer,
    LandingPageSerializer,
    LearningPathDetailSerializer,
    LearningPathListSerializer,
    OrganizationInquiryCreateSerializer,
    WorkshopDetailSerializer,
    WorkshopListSerializer,
    WorkshopRegistrationCreateSerializer,
)

logger = logging.getLogger(__name__)


# -- Pagination ---------------------------------------------------------------


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


# -- Scoped throttles ---------------------------------------------------------


class CourseInquiryThrottle(AnonRateThrottle):
    scope = "education_course_inquiry"


class OrgInquiryThrottle(AnonRateThrottle):
    scope = "education_org_inquiry"


class WorkshopRegisterThrottle(AnonRateThrottle):
    scope = "education_workshop_register"


# -- Taxonomy viewsets --------------------------------------------------------


class CourseCategoryViewSet(ReadOnlyModelViewSet):
    queryset = CourseCategory.objects.filter(is_active=True).order_by("order", "name")
    serializer_class = CourseCategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination


class AudienceTypeViewSet(ReadOnlyModelViewSet):
    queryset = AudienceType.objects.filter(is_active=True).order_by("order", "name")
    serializer_class = AudienceTypeSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination


# -- Course viewset -----------------------------------------------------------


class CourseViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = (
            Course.objects.filter(status__in=["published", "coming_soon"])
            .select_related("category")
            .prefetch_related("audiences", "instructors")
        )

        category = self.request.query_params.get("category")
        audience = self.request.query_params.get("audience")
        difficulty = self.request.query_params.get("difficulty")
        course_format = self.request.query_params.get("format")
        featured = self.request.query_params.get("featured")

        if category:
            queryset = queryset.filter(category__slug=category)
        if audience:
            queryset = queryset.filter(audiences__slug=audience).distinct()
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if course_format:
            queryset = queryset.filter(format=course_format)
        if featured and featured.lower() in ("true", "1", "yes"):
            queryset = queryset.filter(is_featured=True)

        return queryset.order_by("-is_featured", "-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CourseDetailSerializer
        return CourseListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# -- Guide viewset ------------------------------------------------------------


class GuideViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = (
            EducationGuide.objects.filter(status="published")
            .select_related("category", "author")
            .prefetch_related("audiences")
        )

        category = self.request.query_params.get("category")
        audience = self.request.query_params.get("audience")
        difficulty = self.request.query_params.get("difficulty")
        featured = self.request.query_params.get("featured")

        if category:
            queryset = queryset.filter(category__slug=category)
        if audience:
            queryset = queryset.filter(audiences__slug=audience).distinct()
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if featured and featured.lower() in ("true", "1", "yes"):
            queryset = queryset.filter(is_featured=True)

        return queryset.order_by("-is_featured", "-published_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GuideDetailSerializer
        return GuideListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        EducationGuide.objects.filter(pk=instance.pk).update(
            view_count=F("view_count") + 1
        )
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# -- Workshop viewset ---------------------------------------------------------


class WorkshopViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = EducationWorkshop.objects.select_related(
            "category", "instructor"
        ).prefetch_related("audiences")

        workshop_format = self.request.query_params.get("format")
        workshop_status = self.request.query_params.get("status")
        category = self.request.query_params.get("category")

        if workshop_format:
            queryset = queryset.filter(format=workshop_format)
        if workshop_status:
            queryset = queryset.filter(status=workshop_status)
        if category:
            queryset = queryset.filter(category__slug=category)

        return queryset.order_by("-is_featured", "-date")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return WorkshopDetailSerializer
        return WorkshopListSerializer


# -- LearningPath viewset -----------------------------------------------------


class LearningPathViewSet(ReadOnlyModelViewSet):
    queryset = (
        LearningPath.objects.filter(is_active=True)
        .select_related("audience")
        .prefetch_related("modules")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LearningPathDetailSerializer
        return LearningPathListSerializer


# -- LandingPage view ---------------------------------------------------------


class LandingPageDetailView(RetrieveAPIView):
    serializer_class = LandingPageSerializer
    permission_classes = [AllowAny]
    lookup_field = "page_type"

    def get_queryset(self):
        return LandingPage.objects.filter(is_active=True).prefetch_related(
            "featured_courses"
        )


# -- Write-only views (form submissions) --------------------------------------


class CourseInquiryCreateView(CreateAPIView):
    serializer_class = CourseInquiryCreateSerializer
    permission_classes = [AllowAny]
    throttle_classes = [CourseInquiryThrottle]

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.course:
            Course.objects.filter(pk=instance.course.pk).update(
                interest_count=F("interest_count") + 1
            )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrganizationInquiryCreateView(CreateAPIView):
    serializer_class = OrganizationInquiryCreateSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OrgInquiryThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WorkshopRegistrationCreateView(CreateAPIView):
    serializer_class = WorkshopRegistrationCreateSerializer
    permission_classes = [AllowAny]
    throttle_classes = [WorkshopRegisterThrottle]

    def perform_create(self, serializer):
        workshop = EducationWorkshop.objects.get(slug=self.kwargs["slug"])
        instance = serializer.save(workshop=workshop)
        EducationWorkshop.objects.filter(pk=instance.workshop.pk).update(
            registration_count=F("registration_count") + 1
        )
        return instance

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
