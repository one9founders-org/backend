"""
Hugging Face Models Scraper.
Scrapes new AI models from Hugging Face using their API.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.scraper_settings import HuggingFaceConfig  # noqa: E402
from utils.logger import ScraperLogger, setup_logging  # noqa: E402
from utils.output import OutputWriter, normalize_item  # noqa: E402
from utils.rate_limiter import RateLimiter  # noqa: E402


class HuggingFaceScraper:
    """Scraper for Hugging Face models using their API."""

    def __init__(
        self,
        days_back: int = HuggingFaceConfig.DEFAULT_DAYS_BACK,
        limit: int = HuggingFaceConfig.DEFAULT_LIMIT,
        min_downloads: int = HuggingFaceConfig.MIN_DOWNLOADS,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize Hugging Face scraper.

        Args:
            days_back: Number of days back to filter models
            limit: Maximum number of models to scrape
            min_downloads: Minimum download count filter
            output_dir: Directory for output files
        """
        self.days_back = days_back
        self.limit = limit
        self.min_downloads = min_downloads
        self.output_dir = output_dir or HuggingFaceConfig.OUTPUT_DIR

        self.logger: ScraperLogger = setup_logging(
            "huggingface", HuggingFaceConfig.LOG_DIR
        )
        self.rate_limiter = RateLimiter(min_delay=1.0, max_delay=3.0)
        self.output_writer = OutputWriter("HuggingFace", self.output_dir)

        self.cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()

        retry_strategy = Retry(
            total=HuggingFaceConfig.MAX_RETRIES,
            backoff_factor=HuggingFaceConfig.RETRY_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update(
            {
                "User-Agent": HuggingFaceConfig.USER_AGENT,
                "Accept": "application/json",
            }
        )

        return session

    def _fetch_models_list(self) -> List[Dict[str, Any]]:
        """Fetch list of models from Hugging Face API."""
        models: List[Dict[str, Any]] = []
        offset = 0
        batch_size = 100

        self.logger.info("Fetching models from Hugging Face API")

        while len(models) < self.limit * 3:
            self.rate_limiter.wait()

            params = {
                "sort": "lastModified",
                "direction": "-1",
                "limit": batch_size,
                "offset": offset,
                "full": "true",
            }

            try:
                response = self.session.get(
                    HuggingFaceConfig.MODELS_API_URL,
                    params=params,
                    timeout=HuggingFaceConfig.REQUEST_TIMEOUT,
                )
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                for model in batch:
                    last_modified = model.get("lastModified", "")
                    if last_modified:
                        try:
                            modified_date = datetime.fromisoformat(
                                last_modified.replace("Z", "+00:00")
                            ).replace(tzinfo=None)

                            if modified_date < self.cutoff_date:
                                self.logger.info(
                                    f"Reached cutoff date at offset {offset}"
                                )
                                return models
                        except (ValueError, TypeError):
                            pass

                    downloads = model.get("downloads", 0)
                    if downloads >= self.min_downloads:
                        models.append(model)

                offset += batch_size
                self.logger.info(
                    f"Fetched {len(batch)} models, total qualifying: {len(models)}"
                )

                if len(batch) < batch_size:
                    break

            except requests.RequestException as e:
                self.logger.error(f"Error fetching models: {e}")
                break

        return models[: self.limit]

    def _get_model_details(self, model_id: str) -> Dict[str, Any]:
        """Fetch detailed information for a specific model."""
        details: Dict[str, Any] = {
            "readme": "",
            "spaces": [],
        }

        self.rate_limiter.wait()

        try:
            response = self.session.get(
                f"{HuggingFaceConfig.API_BASE_URL}/models/{model_id}",
                timeout=HuggingFaceConfig.REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()

            siblings = data.get("siblings", [])
            for sibling in siblings:
                if sibling.get("rfilename") == "README.md":
                    readme_url = f"https://huggingface.co/{model_id}/raw/main/README.md"
                    try:
                        readme_response = self.session.get(
                            readme_url,
                            timeout=HuggingFaceConfig.REQUEST_TIMEOUT,
                        )
                        if readme_response.status_code == 200:
                            readme_content = readme_response.text
                            if len(readme_content) > 5000:
                                readme_content = readme_content[:5000] + "..."
                            details["readme"] = readme_content
                    except requests.RequestException:
                        pass
                    break

            spaces = data.get("spaces", [])
            if spaces:
                details["spaces"] = spaces[:10]

        except requests.RequestException as e:
            self.logger.warning(f"Error fetching model details for {model_id}: {e}")

        return details

    def _extract_model_info(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and normalize model information."""
        model_id = model.get("modelId", model.get("id", ""))

        author = ""
        model_name = model_id
        if "/" in model_id:
            parts = model_id.split("/", 1)
            author = parts[0]
            model_name = parts[1]

        pipeline_tag = model.get("pipeline_tag", "")
        task_type = pipeline_tag or "unknown"

        tags = model.get("tags", [])

        framework = ""
        framework_tags = ["pytorch", "tensorflow", "jax", "transformers", "diffusers"]
        for tag in tags:
            if tag.lower() in framework_tags:
                framework = tag
                break

        license_info = ""
        for tag in tags:
            if tag.startswith("license:"):
                license_info = tag.replace("license:", "")
                break

        return {
            "model_id": model_id,
            "model_name": model_name,
            "author": author,
            "description": model.get("description", ""),
            "task_type": task_type,
            "framework": framework,
            "license": license_info,
            "downloads": model.get("downloads", 0),
            "likes": model.get("likes", 0),
            "last_modified": model.get("lastModified", ""),
            "created_at": model.get("createdAt", ""),
            "url": f"{HuggingFaceConfig.BASE_URL}/{model_id}",
            "tags": tags,
            "library_name": model.get("library_name", ""),
            "private": model.get("private", False),
        }

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Execute the scraping process.

        Returns:
            List of normalized model items
        """
        self.logger.info(
            f"Starting Hugging Face scrape (days_back={self.days_back}, "
            f"limit={self.limit}, min_downloads={self.min_downloads})"
        )

        try:
            models = self._fetch_models_list()
            self.logger.info(f"Found {len(models)} qualifying models")

            for i, model in enumerate(models):
                model_id = model.get("modelId", model.get("id", ""))
                self.logger.info(f"Processing model {model_id} ({i+1}/{len(models)})")

                model_info = self._extract_model_info(model)

                details = self._get_model_details(model_id)
                model_info.update(details)

                summary = (
                    model_info.get("readme", "")[:500]
                    if model_info.get("readme")
                    else ""
                )
                description = model_info.get("description", "") or summary

                normalized = normalize_item(
                    title=model_info.get("model_name", ""),
                    description=description,
                    url=model_info.get("url", ""),
                    external_url="",
                    category=model_info.get("task_type", ""),
                    tags=model_info.get("tags", []),
                    metrics={
                        "downloads": model_info.get("downloads", 0),
                        "likes": model_info.get("likes", 0),
                        "framework": model_info.get("framework", ""),
                        "license": model_info.get("license", ""),
                    },
                    images=[],
                    raw=model_info,
                )
                self.output_writer.add_item(normalized)

            self.logger.info(
                f"Scraping complete. Total items: {self.output_writer.count}"
            )
            return self.output_writer.items

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}", exc_info=True)
            raise

    def save_output(self, output_path: Optional[Path] = None) -> Path:
        """
        Save the scraped data to a JSON file.

        Args:
            output_path: Optional specific path for the output file

        Returns:
            Path to the saved file
        """
        if output_path:
            return self.output_writer.write_to_path(output_path)
        return self.output_writer.write()


def main() -> None:
    """CLI entry point for Hugging Face scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape new models from Hugging Face")
    parser.add_argument(
        "--limit",
        type=int,
        default=HuggingFaceConfig.DEFAULT_LIMIT,
        help=f"Max models to scrape (default: {HuggingFaceConfig.DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=HuggingFaceConfig.DEFAULT_DAYS_BACK,
        help=f"Days back to filter (default: {HuggingFaceConfig.DEFAULT_DAYS_BACK})",
    )
    parser.add_argument(
        "--min-downloads",
        type=int,
        default=HuggingFaceConfig.MIN_DOWNLOADS,
        help=f"Minimum download count (default: {HuggingFaceConfig.MIN_DOWNLOADS})",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: auto-generated in output directory)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Placeholder for CLI consistency (API-based, always headless)",
    )

    args = parser.parse_args()

    scraper = HuggingFaceScraper(
        days_back=args.days_back,
        limit=args.limit,
        min_downloads=args.min_downloads,
    )

    try:
        scraper.scrape()
        output_path = args.output
        if output_path:
            saved_path = scraper.save_output(Path(output_path))
        else:
            saved_path = scraper.save_output()

        print(f"Output saved to: {saved_path}")
        print(f"Total items scraped: {scraper.output_writer.count}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
