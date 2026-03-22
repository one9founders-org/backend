from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import PaperStatsView, PaperTrendingView, PaperViewSet

router = SimpleRouter()
router.register(r"", PaperViewSet, basename="paper")

urlpatterns = [
    path("trending/", PaperTrendingView.as_view(), name="paper-trending"),
    path("stats/", PaperStatsView.as_view(), name="paper-stats"),
    path("", include(router.urls)),
]
