from django.urls import path

from .extension_views import extension_lookup, extension_suggest

urlpatterns = [
    path("lookup/", extension_lookup, name="extension-lookup"),
    path("suggest/", extension_suggest, name="extension-suggest"),
]
