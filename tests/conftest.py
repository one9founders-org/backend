import pytest
from django.test.utils import override_settings


# Override settings for testing
@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Enable database access for all tests.
    """
    pass


@pytest.fixture(autouse=True)
def use_test_settings():
    """
    Override settings for testing.
    """
    with override_settings(
        OPENAI_API_KEY="test-key",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        CELERY_TASK_ALWAYS_EAGER=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        },
    ):
        yield
