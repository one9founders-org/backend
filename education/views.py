from django.db.models import F
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
    AudienceType,
    Course,
    CourseCategory,
    CourseInquiry,
    EducationGuide,
    EducationWorkshop,
    Instructor,
    LandingPage,
    LearningPath,
    OrganizationInquiry,
    WorkshopRegistration,
)
from .serializers import (
    AudienceTypeSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseInquiryCreateSerializer,
    CourseListSerializer,
    EducationGuideDetailSerializer,
    EducationGuideListSerializer,
    EducationWorkshopDetailSerializer,
    EducationWorkshopListSerializer,
    InstructorSerializer,
    LandingPageSerializer,
    LearningPathDetailSerializer,
    LearningPathListSerializer,
    OrganizationInquiryCreateSerializer,
    WorkshopRegistrationCreateSerializer,
)


class CourseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CourseCategory.objects.filter(is_active=True)
    serializer_class = CourseCategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class AudienceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AudienceType.objects.filter(is_active=True)
    serializer_class = AudienceTypeSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class InstructorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Instructor.objects.filter(is_active=True)
    serializer_class = InstructorSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Course.objects.filter(status="published")
        .select_related("category")
        .prefetch_related("audiences", "instructors", "modules", "faqs")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CourseDetailSerializer
        return CourseListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        audience = self.request.query_params.get("audience")
        difficulty = self.request.query_params.get("difficulty")
        course_format = self.request.query_params.get("format")
        featured = self.request.query_params.get("featured")

        if category:
            queryset = queryset.filter(category__slug=category)
        if audience:
            queryset = queryset.filter(audiences__slug=audience)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)
        if course_format:
            queryset = queryset.filter(format=course_format)
        if featured:
            queryset = queryset.filter(is_featured=True)

        return queryset.distinct()

    @action(detail=True, methods=["post"])
    def express_interest(self, request, slug=None):
        """Increment interest_count for a course."""
        course = self.get_object()
        Course.objects.filter(pk=course.pk).update(
            interest_count=F("interest_count") + 1
        )
        course.refresh_from_db()
        return Response({"interest_count": course.interest_count})


class EducationGuideViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        EducationGuide.objects.filter(status="published")
        .select_related("category", "author", "related_course")
        .prefetch_related("audiences")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EducationGuideDetailSerializer
        return EducationGuideListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        audience = self.request.query_params.get("audience")
        difficulty = self.request.query_params.get("difficulty")

        if category:
            queryset = queryset.filter(category__slug=category)
        if audience:
            queryset = queryset.filter(audiences__slug=audience)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        return queryset.distinct()


class EducationWorkshopViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        EducationWorkshop.objects.exclude(status="cancelled")
        .select_related("category", "instructor")
        .prefetch_related("audiences")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EducationWorkshopDetailSerializer
        return EducationWorkshopListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        workshop_status = self.request.query_params.get("status")
        workshop_format = self.request.query_params.get("format")

        if workshop_status:
            queryset = queryset.filter(status=workshop_status)
        if workshop_format:
            queryset = queryset.filter(format=workshop_format)

        return queryset


class LearningPathViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        LearningPath.objects.filter(is_active=True)
        .select_related("audience")
        .prefetch_related("modules__courses", "modules__guides", "modules__workshops")
    )
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return LearningPathDetailSerializer
        return LearningPathListSerializer


class LandingPageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LandingPage.objects.filter(is_active=True).prefetch_related(
        "featured_courses"
    )
    serializer_class = LandingPageSerializer
    permission_classes = [AllowAny]
    lookup_field = "page_type"


class CourseInquiryViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = CourseInquiry.objects.all()
    serializer_class = CourseInquiryCreateSerializer
    permission_classes = [AllowAny]


class OrganizationInquiryViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = OrganizationInquiry.objects.all()
    serializer_class = OrganizationInquiryCreateSerializer
    permission_classes = [AllowAny]


class WorkshopRegistrationViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = WorkshopRegistration.objects.all()
    serializer_class = WorkshopRegistrationCreateSerializer
    permission_classes = [AllowAny]
