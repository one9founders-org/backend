from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AudienceTypeViewSet,
    CourseCategoryViewSet,
    CourseInquiryViewSet,
    CourseViewSet,
    EducationGuideViewSet,
    EducationWorkshopViewSet,
    InstructorViewSet,
    LandingPageViewSet,
    LearningPathViewSet,
    OrganizationInquiryViewSet,
    WorkshopRegistrationViewSet,
)

router = DefaultRouter()
router.register(r"categories", CourseCategoryViewSet, basename="edu-category")
router.register(r"audiences", AudienceTypeViewSet, basename="edu-audience")
router.register(r"instructors", InstructorViewSet, basename="edu-instructor")
router.register(r"courses", CourseViewSet, basename="edu-course")
router.register(r"guides", EducationGuideViewSet, basename="edu-guide")
router.register(r"workshops", EducationWorkshopViewSet, basename="edu-workshop")
router.register(r"learning-paths", LearningPathViewSet, basename="edu-learning-path")
router.register(r"landing-pages", LandingPageViewSet, basename="edu-landing-page")
router.register(
    r"inquiries/course", CourseInquiryViewSet, basename="edu-course-inquiry"
)
router.register(
    r"inquiries/organization",
    OrganizationInquiryViewSet,
    basename="edu-organization-inquiry",
)
router.register(
    r"workshop-registrations",
    WorkshopRegistrationViewSet,
    basename="edu-workshop-registration",
)

urlpatterns = [
    path("", include(router.urls)),
]
