from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AudienceTypeViewSet,
    CourseCategoryViewSet,
    CourseInquiryCreateView,
    CourseViewSet,
    GuideViewSet,
    LandingPageDetailView,
    LearningPathViewSet,
    OrganizationInquiryCreateView,
    WorkshopRegistrationCreateView,
    WorkshopViewSet,
)

router = DefaultRouter()
router.register(r"categories", CourseCategoryViewSet, basename="edu-category")
router.register(r"audiences", AudienceTypeViewSet, basename="edu-audience")
router.register(r"courses", CourseViewSet, basename="edu-course")
router.register(r"guides", GuideViewSet, basename="edu-guide")
router.register(r"workshops", WorkshopViewSet, basename="edu-workshop")
router.register(r"learning-paths", LearningPathViewSet, basename="edu-learning-path")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "landing-pages/<str:page_type>/",
        LandingPageDetailView.as_view(),
        name="edu-landing-page-detail",
    ),
    path(
        "inquiries/course/",
        CourseInquiryCreateView.as_view(),
        name="edu-course-inquiry-create",
    ),
    path(
        "inquiries/organization/",
        OrganizationInquiryCreateView.as_view(),
        name="edu-org-inquiry-create",
    ),
    path(
        "workshops/<slug:slug>/register/",
        WorkshopRegistrationCreateView.as_view(),
        name="edu-workshop-register",
    ),
]
