"""
Rate limiting utilities for respectful web scraping.
Implements randomized delays to avoid detection and respect server resources.
"""

import random
import time
from typing import Optional

from config.scraper_settings import ScraperConfig


class RateLimiter:
    """
    Rate limiter with randomized delays for web scraping.
    Helps avoid detection and respects server resources.
    """

    def __init__(
        self,
        min_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            min_delay: Minimum delay between requests in seconds
            max_delay: Maximum delay between requests in seconds
        """
        self.min_delay = min_delay or ScraperConfig.MIN_DELAY
        self.max_delay = max_delay or ScraperConfig.MAX_DELAY
        self.last_request_time: Optional[float] = None

    def wait(self) -> float:
        """
        Wait for a randomized delay before the next request.

        Returns:
            The actual delay time in seconds
        """
        if self.last_request_time is not None:
            elapsed = time.time() - self.last_request_time
            delay = random.uniform(self.min_delay, self.max_delay)

            if elapsed < delay:
                sleep_time = delay - elapsed
                time.sleep(sleep_time)
            else:
                sleep_time = 0.0
        else:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)
            sleep_time = delay

        self.last_request_time = time.time()
        return sleep_time

    def reset(self) -> None:
        """Reset the rate limiter state."""
        self.last_request_time = None
