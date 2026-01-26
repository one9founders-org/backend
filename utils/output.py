"""
Output utilities for standardized JSON output from scrapers.
Ensures all scrapers emit data in the normalized schema required for n8n ingestion.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def normalize_item(
    title: str,
    description: str,
    url: str,
    external_url: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    images: Optional[List[str]] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize a scraped item to the standard output schema.

    Args:
        title: Item title/name
        description: Item description
        url: Primary URL (source page)
        external_url: External website URL (if different from source)
        category: Primary category
        tags: List of tags/topics
        metrics: Dictionary of metrics (upvotes, downloads, etc.)
        images: List of image URLs
        raw: Raw scraped data for reference

    Returns:
        Normalized item dictionary
    """
    return {
        "title": title or "",
        "description": description or "",
        "url": url or "",
        "external_url": external_url or "",
        "category": category or "",
        "tags": tags or [],
        "metrics": metrics or {},
        "images": images or [],
        "raw": raw or {},
    }


class OutputWriter:
    """
    Handles writing scraper output to JSON files in the standardized format.
    """

    def __init__(
        self,
        source: str,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        """
        Initialize output writer.

        Args:
            source: Name of the data source (e.g., "ProductHunt", "TAAFT")
            output_dir: Directory to write output files
        """
        self.source = source
        self.output_dir = Path(output_dir) if output_dir else self._default_output_dir()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.items: List[Dict[str, Any]] = []
        self.scrape_date = datetime.utcnow().isoformat() + "Z"

    def _default_output_dir(self) -> Path:
        return Path(__file__).parent.parent / "output"

    def add_item(self, item: Dict[str, Any]) -> None:
        """Add a normalized item to the output."""
        self.items.append(item)

    def add_items(self, items: List[Dict[str, Any]]) -> None:
        """Add multiple normalized items to the output."""
        self.items.extend(items)

    def get_output(self) -> Dict[str, Any]:
        """
        Get the complete output in the standardized format.

        Returns:
            Dictionary with source, scrape_date, and items
        """
        return {
            "source": self.source,
            "scrape_date": self.scrape_date,
            "items": self.items,
        }

    def write(
        self,
        filename: Optional[str] = None,
        indent: int = 2,
    ) -> Path:
        """
        Write output to a JSON file.

        Args:
            filename: Optional custom filename (default: source_timestamp.json)
            indent: JSON indentation level

        Returns:
            Path to the written file
        """
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.source.lower()}_{timestamp}.json"

        output_path = self.output_dir / filename
        output_data = self.get_output()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=indent, ensure_ascii=False)

        return output_path

    def write_to_path(
        self,
        path: Union[str, Path],
        indent: int = 2,
    ) -> Path:
        """
        Write output to a specific path.

        Args:
            path: Full path to write the output file
            indent: JSON indentation level

        Returns:
            Path to the written file
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_data = self.get_output()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=indent, ensure_ascii=False)

        return output_path

    def to_json(self, indent: int = 2) -> str:
        """
        Get output as a JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string of the output
        """
        return json.dumps(self.get_output(), indent=indent, ensure_ascii=False)

    @property
    def count(self) -> int:
        """Return the number of items collected."""
        return len(self.items)

    def clear(self) -> None:
        """Clear all collected items."""
        self.items = []
        self.scrape_date = datetime.utcnow().isoformat() + "Z"
