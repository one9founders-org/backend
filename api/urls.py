from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import pipeline_views, views
from .auth_views import get_current_user, google_auth, login_user, register_user
from .smart_search_views import decompose_task_search, smart_search_tools

router = DefaultRouter()
router.register(r"tools", views.ToolViewSet, basename="tool")
router.register(r"categories", views.CategoryViewSet, basename="category")
router.register(r"reviews", views.ReviewViewSet, basename="review")
router.register(r"deals", views.DealViewSet, basename="deal")
router.register(r"news", views.NewsViewSet, basename="news")
router.register(r"submissions", views.ToolSubmissionViewSet, basename="submission")
router.register(r"guides", views.GuideViewSet, basename="guide")
router.register(r"labs", views.LabViewSet, basename="lab")
router.register(r"workshops", views.WorkshopViewSet, basename="workshop")

# Pipeline routers
router.register(
    r"pipeline/scraped", pipeline_views.ScrapedItemViewSet, basename="scraped-item"
)
router.register(
    r"pipeline/qualified",
    pipeline_views.QualifiedNewsItemViewSet,
    basename="qualified-item",
)
router.register(
    r"pipeline/drafts", pipeline_views.NewsDraftViewSet, basename="news-draft"
)
router.register(
    r"pipeline/published",
    pipeline_views.PublishedArticleViewSet,
    basename="published-article",
)
router.register(
    r"pipeline/runs", pipeline_views.PipelineRunViewSet, basename="pipeline-run"
)

urlpatterns = [
    # Search and Actions
    path("tools/search/", views.search_tools, name="tool-search"),
    path("tools/smart-search/", smart_search_tools, name="tool-smart-search"),
    path(
        "tools/decompose-search/", decompose_task_search, name="tool-decompose-search"
    ),
    path("tools/add/", views.add_tool, name="tool-add"),
    path("internal/sync-lacreme/", views.sync_lacreme, name="sync-lacreme"),
    path(
        "newsletter/subscribe/", views.subscribe_newsletter, name="newsletter-subscribe"
    ),
    # Tracking endpoints
    path("track/usage/", views.track_tool_usage, name="track-tool-usage"),
    path("track/click/", views.track_tool_click, name="track-tool-click"),
    path("track/search/", views.track_search_query, name="track-search-query"),
    path("tools/trending/", views.trending_tools, name="trending-tools"),
    path(
        "tools/<int:tool_id>/usage-count/",
        views.tool_usage_count,
        name="tool-usage-count",
    ),
    # Pricing endpoints
    path("config/pricing/", views.pricing_config, name="pricing-config"),
    path(
        "tools/<slug:tool_slug>/report-pricing/",
        views.report_pricing,
        name="report-pricing",
    ),
    # News upvote endpoints
    path("news/<int:news_id>/upvote/", views.upvote_news, name="news-upvote"),
    path(
        "news/<int:news_id>/upvote/remove/",
        views.remove_upvote_news,
        name="news-upvote-remove",
    ),
    # Authentication (also available at root /auth/* via config/urls.py)
    path("auth/register/", register_user, name="api_register_user"),
    path("auth/login/", login_user, name="api_login_user"),
    path("auth/google/", google_auth, name="api_google_auth"),
    path("auth/me/", get_current_user, name="api_current_user"),
    # Pipeline API
    path(
        "pipeline/ingest/", pipeline_views.ingest_scraped_data, name="pipeline-ingest"
    ),
    path("pipeline/run/", pipeline_views.run_pipeline, name="pipeline-run-trigger"),
    path("pipeline/scrape/", pipeline_views.run_scraper, name="pipeline-scrape"),
    path("pipeline/stats/", pipeline_views.pipeline_stats, name="pipeline-stats"),
    path("pipeline/config/", pipeline_views.pipeline_config, name="pipeline-config"),
    path(
        "pipeline/toggle-publishing/",
        pipeline_views.toggle_publishing,
        name="pipeline-toggle-publishing",
    ),
    path("pipeline/feed/", pipeline_views.news_feed, name="pipeline-news-feed"),
    # REST API
    path("", include(router.urls)),
]
