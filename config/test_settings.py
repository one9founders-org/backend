import os

from config.settings import *  # noqa: F401, F403
from config.settings import BASE_DIR

# Override test-specific settings
DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME", "test_one9founders"),
        "USER": os.getenv("DATABASE_USER", "one9testuser"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", "one9testpass"),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
    }
}

# Simplify password hashing for faster tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use a fast local cache instead of production Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Disable Sentry for tests
SENTRY_DSN = ""

# Disable S3 and use local storage for tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
MEDIA_ROOT = BASE_DIR / "test_media"

# Disable FAISS S3 uploading/downloading in tests
S3_FAISS_BUCKET_NAME = None
S3_INDEX_FILE_PATH = None

# Ensure the news pipeline doesn't actually try to scrape external RSS in basic tests
SKIP_NEWS_SCRAPING = True
