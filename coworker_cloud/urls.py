from django.urls import path

from . import views_broker, views_oidc

urlpatterns = [
    # Human landing
    path("cloud/", views_broker.cloud_home, name="coworker_cloud_home"),
    # Auth0-shaped OIDC (OpenWorker cloud_auth_domain points here)
    path("authorize", views_oidc.authorize, name="coworker_cloud_authorize"),
    path("authorize/", views_oidc.authorize),
    path("oauth/token", views_oidc.oauth_token, name="coworker_cloud_token"),
    path("oauth/token/", views_oidc.oauth_token),
    path(
        "oidc/google/start",
        views_oidc.authorize_google_redirect,
        name="coworker_cloud_google_redirect",
    ),
    path("oidc/google/callback", views_oidc.google_oidc_callback),
    # Broker API (OpenWorker cloud_base_url)
    path("v1/auth/callback", views_broker.auth_callback_bounce),
    path("v1/auth/callback/", views_broker.auth_callback_bounce),
    path("v1/me", views_broker.me),
    path("v1/me/", views_broker.me),
    path("v1/connections", views_broker.connections),
    path("v1/connections/", views_broker.connections),
    path(
        "v1/connections/<str:connection_id>/disconnect",
        views_broker.connection_disconnect,
    ),
    path(
        "v1/connections/<str:connection_id>/disconnect/",
        views_broker.connection_disconnect,
    ),
    path("v1/telemetry/events", views_broker.telemetry_events),
    path("v1/telemetry/events/", views_broker.telemetry_events),
    path("v1/oauth/<str:provider>/start", views_broker.oauth_start),
    path("v1/oauth/<str:provider>/start/", views_broker.oauth_start),
    path("v1/oauth/<str:provider>/refresh", views_broker.oauth_refresh),
    path("v1/oauth/<str:provider>/refresh/", views_broker.oauth_refresh),
    path("v1/oauth/google/callback", views_broker.oauth_google_callback),
    path("v1/oauth/google/callback/", views_broker.oauth_google_callback),
]
