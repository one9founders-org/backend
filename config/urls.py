from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from rag_directory.search import global_search


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response(
        {
            "status": "ok",
            "version": "1.0.0",
            "environment": "development" if settings.DEBUG else "production",
        }
    )


urlpatterns = [
    # Health and Admin
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Rich Text Editor
    path("summernote/", include("django_summernote.urls")),
    # API
    path("", include("api.urls")),
    # Extension API (versioned)
    path("api/v1/extension/", include("api.extension_urls")),
    # Education
    path("api/education/", include("education.urls")),
    # Sentiment Analysis
    path("api/sentiment/", include("sentiment.urls")),
    # Agents Directory
    path("", include("agents.urls")),
    # RAG & Vector DB Directory
    path("api/v1/rag/", include("rag_directory.urls")),
    # Research Papers
    path("api/v1/papers/", include("research_papers.urls")),
    # Global Search
    path("api/v1/search/", global_search, name="global-search"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
