from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import register_user, login_user, google_auth

router = DefaultRouter()
router.register(r'tools', views.ToolViewSet, basename='tool')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'reviews', views.ReviewViewSet, basename='review')
router.register(r'deals', views.DealViewSet, basename='deal')
router.register(r'news', views.NewsViewSet, basename='news')
router.register(r'submissions', views.ToolSubmissionViewSet, basename='submission')

urlpatterns = [
    path('', include(router.urls)),
    path('health/', views.health_check, name='health_check'),
    path('newsletter/subscribe/', views.subscribe_newsletter, name='subscribe_newsletter'),
    path('auth/register/', register_user, name='register_user'),
    path('auth/login/', login_user, name='login_user'),
    path('auth/google/', google_auth, name='google_auth'),
]
