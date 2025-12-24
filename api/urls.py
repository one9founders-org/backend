from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .auth_views import google_auth, login_user, register_user

router = DefaultRouter()
router.register(r"tools", views.ToolViewSet, basename="tool")
router.register(r"categories", views.CategoryViewSet, basename="category")
router.register(r"reviews", views.ReviewViewSet, basename="review")
router.register(r"deals", views.DealViewSet, basename="deal")
router.register(r"news", views.NewsViewSet, basename="news")
router.register(r"submissions", views.ToolSubmissionViewSet, basename="submission")

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
    path("tools/search/", views.search_tools, name="tool-search"),
    path("tools/add/", views.add_tool, name="tool-add"),
    path(
        "newsletter/subscribe/", views.subscribe_newsletter, name="newsletter-subscribe"
    ),
    path("auth/register/", register_user, name="register_user"),
    path("auth/login/", login_user, name="login_user"),
    path("auth/google/", google_auth, name="google_auth"),
    path("", include(router.urls)),
]
