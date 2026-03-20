from django.urls import path

from .views import AgentCategoryListView, AgentStatsView, AgentViewSet

urlpatterns = [
    path(
        "api/agents/",
        AgentViewSet.as_view({"get": "list"}),
        name="agent-list",
    ),
    path(
        "api/agents/stats/",
        AgentStatsView.as_view(),
        name="agent-stats",
    ),
    path(
        "api/agents/categories/",
        AgentCategoryListView.as_view(),
        name="agent-categories",
    ),
    path(
        "api/agents/<slug:slug>/",
        AgentViewSet.as_view({"get": "retrieve"}),
        name="agent-detail",
    ),
]
