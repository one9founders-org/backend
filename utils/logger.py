"""
Structured JSON logging for AI News Automation scrapers.
Provides consistent logging format across all scrapers.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON-structured log entries."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        return json.dumps(log_entry)


class ScraperLogger(logging.Logger):
    """Extended logger with structured data support."""

    def _log_with_data(
        self,
        level: int,
        msg: str,
        data: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if data:
            extra = kwargs.get("extra", {})
            extra["extra_data"] = data
            kwargs["extra"] = extra
        super()._log(level, msg, args, **kwargs)

    def info_with_data(
        self, msg: str, data: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> None:
        self._log_with_data(logging.INFO, msg, data, **kwargs)

    def warning_with_data(
        self, msg: str, data: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> None:
        self._log_with_data(logging.WARNING, msg, data, **kwargs)

    def error_with_data(
        self, msg: str, data: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> None:
        self._log_with_data(logging.ERROR, msg, data, **kwargs)


logging.setLoggerClass(ScraperLogger)


def setup_logging(
    scraper_name: str,
    log_dir: Optional[Path] = None,
    log_level: int = logging.INFO,
    console_output: bool = True,
) -> ScraperLogger:
    """
    Set up logging for a scraper with both file and console handlers.

    Args:
        scraper_name: Name of the scraper (used for log file naming)
        log_dir: Directory to store log files
        log_level: Logging level (default: INFO)
        console_output: Whether to also output to console

    Returns:
        Configured ScraperLogger instance
    """
    if log_dir is None:
        log_dir = Path(__file__).parent.parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{scraper_name}_{timestamp}.json"

    logger = logging.getLogger(scraper_name)
    logger.setLevel(log_level)

    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

    logger.propagate = False

    return logger  # type: ignore[return-value]


def get_logger(name: str) -> ScraperLogger:
    """Get an existing logger by name."""
    return logging.getLogger(name)  # type: ignore[return-value]
