# flake8: noqa

import os

from .settings import *

# Test database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_one9founders",
        "USER": "one9testuser",
        "PASSWORD": "one9testpass",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# Use in-memory cache for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Disable logging during tests
LOGGING_CONFIG = None

# Use console email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable CSRF for API tests
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = []

# Test-specific settings
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
