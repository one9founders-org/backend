"""
Configuration settings for the AI News Automation scrapers.
All settings can be overridden via environment variables.
"""

import os
from pathlib import Path
from typing import List, Optional


class ScraperConfig:
    """Base configuration for all scrapers."""

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    MIN_DELAY: float = float(os.getenv("SCRAPER_MIN_DELAY", "2.0"))
    MAX_DELAY: float = float(os.getenv("SCRAPER_MAX_DELAY", "7.0"))

    MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))
    RETRY_BACKOFF_FACTOR: float = float(
        os.getenv("SCRAPER_RETRY_BACKOFF_FACTOR", "2.0")
    )

    REQUEST_TIMEOUT: int = int(os.getenv("SCRAPER_REQUEST_TIMEOUT", "30"))
    PAGE_LOAD_TIMEOUT: int = int(os.getenv("SCRAPER_PAGE_LOAD_TIMEOUT", "60"))

    OUTPUT_DIR: Path = Path(os.getenv("SCRAPER_OUTPUT_DIR", str(BASE_DIR / "output")))
    LOG_DIR: Path = Path(os.getenv("SCRAPER_LOG_DIR", str(BASE_DIR / "logs")))

    USER_AGENT: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    CHROME_BINARY: Optional[str] = os.getenv("CHROME_BINARY", None)
    CHROMEDRIVER_PATH: Optional[str] = os.getenv("CHROMEDRIVER_PATH", None)


class ProductHuntConfig(ScraperConfig):
    """Configuration specific to Product Hunt scraper."""

    BASE_URL: str = "https://www.producthunt.com"
    AI_TOPICS_URL: str = "https://www.producthunt.com/topics/artificial-intelligence"
    DEFAULT_DAYS_BACK: int = 7
    DEFAULT_LIMIT: int = 100


class TAAFTConfig(ScraperConfig):
    """Configuration specific to There's An AI For That scraper."""

    BASE_URL: str = "https://theresanaiforthat.com"
    NEWLY_ADDED_URL: str = "https://theresanaiforthat.com/newly-added/"
    DEFAULT_LIMIT: int = 100
    SCROLL_PAUSE_TIME: float = 2.0
    MAX_SCROLLS: int = 50


class FuturepediaConfig(ScraperConfig):
    """Configuration specific to Futurepedia scraper."""

    BASE_URL: str = "https://www.futurepedia.io"
    DEFAULT_LIMIT_PER_CATEGORY: int = 20
    CATEGORIES: List[str] = [
        "text",
        "image",
        "video",
        "audio",
        "code",
        "business",
        "marketing",
        "productivity",
        "education",
        "lifestyle",
    ]


class HuggingFaceConfig(ScraperConfig):
    """Configuration specific to Hugging Face scraper."""

    API_BASE_URL: str = "https://huggingface.co/api"
    MODELS_API_URL: str = "https://huggingface.co/api/models"
    BASE_URL: str = "https://huggingface.co"
    DEFAULT_DAYS_BACK: int = 7
    DEFAULT_LIMIT: int = 100
    MIN_DOWNLOADS: int = 1000
