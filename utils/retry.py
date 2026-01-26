"""
Retry utilities with exponential backoff for resilient web scraping.
"""

import functools
import time
from typing import Any, Callable, Optional, Tuple, Type, TypeVar, Union

from config.scraper_settings import ScraperConfig

T = TypeVar("T")

ExceptionTypes = Union[Type[Exception], Tuple[Type[Exception], ...]]


def retry_with_backoff(
    max_retries: Optional[int] = None,
    backoff_factor: Optional[float] = None,
    exceptions: ExceptionTypes = Exception,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
        exceptions: Exception types to catch and retry
        on_retry: Optional callback called on each retry with (exception, attempt)

    Returns:
        Decorated function with retry logic
    """
    _max_retries = max_retries or ScraperConfig.MAX_RETRIES
    _backoff_factor = backoff_factor or ScraperConfig.RETRY_BACKOFF_FACTOR

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < _max_retries:
                        delay = _backoff_factor**attempt
                        if on_retry:
                            on_retry(e, attempt + 1)
                        time.sleep(delay)
                    else:
                        raise

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


class RetryContext:
    """
    Context manager for retry logic with exponential backoff.
    Useful for more complex retry scenarios.
    """

    def __init__(
        self,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        exceptions: ExceptionTypes = Exception,
    ) -> None:
        self.max_retries = max_retries or ScraperConfig.MAX_RETRIES
        self.backoff_factor = backoff_factor or ScraperConfig.RETRY_BACKOFF_FACTOR
        self.exceptions = exceptions
        self.attempt = 0
        self.last_exception: Optional[Exception] = None

    def should_retry(self, exception: Exception) -> bool:
        """Check if we should retry after an exception."""
        if not isinstance(exception, self.exceptions):
            return False

        self.last_exception = exception
        self.attempt += 1

        if self.attempt <= self.max_retries:
            delay = self.backoff_factor ** (self.attempt - 1)
            time.sleep(delay)
            return True

        return False

    def reset(self) -> None:
        """Reset the retry context."""
        self.attempt = 0
        self.last_exception = None
