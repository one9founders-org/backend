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
router.register(r"categories", CourseCategoryViewSet, basename="category")
router.register(r"audiences", AudienceTypeViewSet, basename="audience")
router.register(r"instructors", InstructorViewSet, basename="instructor")
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"guides", EducationGuideViewSet, basename="guide")
router.register(r"workshops", EducationWorkshopViewSet, basename="workshop")
router.register(r"learning-paths", LearningPathViewSet, basename="learning-path")
router.register(r"landing-pages", LandingPageViewSet, basename="landing-page")
router.register(r"inquiries/course", CourseInquiryViewSet, basename="course-inquiry")
router.register(
    r"inquiries/organization",
    OrganizationInquiryViewSet,
    basename="organization-inquiry",
)
router.register(
    r"workshop-registrations",
    WorkshopRegistrationViewSet,
    basename="workshop-registration",
)

urlpatterns = [
    path("", include(router.urls)),
]
