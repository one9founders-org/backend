from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RagCategoriesView, RagCompareView, RagToolViewSet

router = DefaultRouter()
router.register(r"tools", RagToolViewSet, basename="rag-tool")

urlpatterns = [
    path("categories/", RagCategoriesView.as_view(), name="rag-categories"),
    path("compare/", RagCompareView.as_view(), name="rag-compare"),
    path("", include(router.urls)),
]
