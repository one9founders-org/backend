from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .auth_views import register_user, login_user, google_auth

router = DefaultRouter()
router.register(r'tools', views.ToolViewSet)
router.register(r'categories', views.CategoryViewSet)
router.register(r'reviews', views.ReviewViewSet)
router.register(r'deals', views.DealViewSet)
router.register(r'news', views.NewsViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('newsletter/subscribe/', views.subscribe_newsletter, name='subscribe_newsletter'),
    path('tools/submit/', views.submit_tool, name='submit_tool'),
    path('seed/', views.seed_database, name='seed_database'),
    path('auth/register/', register_user, name='register_user'),
    path('auth/login/', login_user, name='login_user'),
    path('auth/google/', google_auth, name='google_auth'),
]
