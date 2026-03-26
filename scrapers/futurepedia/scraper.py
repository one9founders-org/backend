"""
Futurepedia AI Tools Scraper.
Scrapes AI tools from futurepedia.io with category-aware scraping.
"""

import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.scraper_settings import FuturepediaConfig  # noqa: E402
from utils.logger import ScraperLogger, setup_logging  # noqa: E402
from utils.output import OutputWriter, normalize_item  # noqa: E402
from utils.rate_limiter import RateLimiter  # noqa: E402
from utils.retry import RetryContext  # noqa: E402
from utils.selenium_driver import create_driver  # noqa: E402


class FuturepediaScraper:
    """Scraper for Futurepedia AI tools with category support."""

    def __init__(
        self,
        headless: bool = True,
        limit_per_category: int = FuturepediaConfig.DEFAULT_LIMIT_PER_CATEGORY,
        categories: Optional[List[str]] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize Futurepedia scraper.

        Args:
            headless: Run browser in headless mode
            limit_per_category: Maximum number of items per category
            categories: List of categories to scrape (default: all configured)
            output_dir: Directory for output files
        """
        self.headless = headless
        self.limit_per_category = limit_per_category
        self.categories = categories or FuturepediaConfig.CATEGORIES
        self.output_dir = output_dir or FuturepediaConfig.OUTPUT_DIR

        self.logger: ScraperLogger = setup_logging(
            "futurepedia", FuturepediaConfig.LOG_DIR
        )
        self.rate_limiter = RateLimiter()
        self.driver: Optional[WebDriver] = None
        self.output_writer = OutputWriter("Futurepedia", self.output_dir)

    def _init_driver(self) -> None:
        """Initialize the Selenium WebDriver."""
        if self.driver is None:
            self.driver = create_driver(headless=self.headless)
            self.logger.info("WebDriver initialized")

    def _close_driver(self) -> None:
        """Close the Selenium WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logger.info("WebDriver closed")

    def _extract_tools_from_page(self, category: str) -> List[Dict[str, Any]]:
        """Extract tool information from the current page."""
        if not self.driver:
            return []

        tools: List[Dict[str, Any]] = []
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        tool_links = soup.find_all("a", href=re.compile(r"/tool/[^/]+"))

        seen_urls: set = set()

        for link in tool_links:
            try:
                href = link.get("href", "")
                if not href or href in seen_urls:
                    continue

                tool_url = (
                    f"{FuturepediaConfig.BASE_URL}{href}"
                    if href.startswith("/")
                    else href
                )
                seen_urls.add(href)

                parent = link.find_parent("div")
                if not parent:
                    parent = link

                name_elem = link.find(["h2", "h3", "strong", "span"])
                tool_name = ""
                if name_elem:
                    tool_name = name_elem.get_text(strip=True)

                if not tool_name or len(tool_name) < 2:
                    slug = href.split("/tool/")[-1] if "/tool/" in href else ""
                    tool_name = slug.replace("-", " ").title()

                if not tool_name:
                    continue

                desc_elem = parent.find("p")
                short_description = ""
                if desc_elem:
                    short_description = desc_elem.get_text(strip=True)

                pricing = {"model": "", "details": ""}
                parent_text = parent.get_text().lower()
                if "free" in parent_text and "trial" in parent_text:
                    pricing["model"] = "free_trial"
                elif "freemium" in parent_text:
                    pricing["model"] = "freemium"
                elif "free" in parent_text:
                    pricing["model"] = "free"
                elif "paid" in parent_text:
                    pricing["model"] = "paid"

                rating = 0.0
                rating_match = re.search(
                    r"(\d+\.?\d*)\s*(?:star|rating|/5)", parent_text
                )
                if rating_match:
                    rating = float(rating_match.group(1))

                img_elem = parent.find("img")
                thumbnail = ""
                if img_elem:
                    thumbnail = img_elem.get("src", "") or img_elem.get("data-src", "")

                tag_elems = parent.find_all("span")
                tags = []
                for tag in tag_elems[:5]:
                    tag_text = tag.get_text(strip=True)
                    if tag_text and len(tag_text) < 30 and tag_text != tool_name:
                        tags.append(tag_text)

                tools.append(
                    {
                        "tool_name": tool_name,
                        "short_description": short_description,
                        "futurepedia_url": tool_url,
                        "primary_category": category,
                        "pricing": pricing,
                        "rating": rating,
                        "tags": tags,
                        "thumbnail_image": thumbnail,
                    }
                )

                if len(tools) >= self.limit_per_category:
                    break

            except Exception as e:
                self.logger.warning(f"Error extracting tool: {e}")
                continue

        return tools

    def _get_tool_details(self, tool_url: str) -> Dict[str, Any]:
        """Fetch additional details from the tool page."""
        details: Dict[str, Any] = {
            "website_url": "",
            "long_description": "",
            "features": [],
            "subcategories": [],
            "verified_status": False,
            "views": 0,
        }

        if not tool_url or not self.driver:
            return details

        retry_ctx = RetryContext(max_retries=2)

        while True:
            try:
                self.rate_limiter.wait()
                self.driver.get(tool_url)

                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2)

                soup = BeautifulSoup(self.driver.page_source, "html.parser")

                external_links = soup.find_all("a", href=re.compile(r"^https?://"))
                for link in external_links:
                    href = link.get("href", "")
                    if "futurepedia" not in href and href:
                        link_text = link.get_text(strip=True).lower()
                        if (
                            "visit" in link_text
                            or "website" in link_text
                            or "try" in link_text
                        ):
                            details["website_url"] = href
                            break

                desc_elems = soup.find_all("p")
                descriptions = []
                for desc in desc_elems[:5]:
                    text = desc.get_text(strip=True)
                    if len(text) > 30:
                        descriptions.append(text)
                details["long_description"] = " ".join(descriptions[:3])

                feature_elems = soup.find_all("li")
                features = []
                for feat in feature_elems[:10]:
                    feat_text = feat.get_text(strip=True)
                    if feat_text and len(feat_text) < 150:
                        features.append(feat_text)
                details["features"] = features

                if "verified" in soup.get_text().lower():
                    details["verified_status"] = True

                views_match = re.search(
                    r"(\d+)\s*(?:views|visits)", soup.get_text(), re.IGNORECASE
                )
                if views_match:
                    details["views"] = int(views_match.group(1).replace(",", ""))

                break

            except (TimeoutException, WebDriverException) as e:
                if retry_ctx.should_retry(e):
                    self.logger.warning(
                        f"Retrying details: {e} (attempt {retry_ctx.attempt})"
                    )
                    continue
                else:
                    self.logger.error(f"Failed to fetch tool details: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Unexpected error fetching tool details: {e}")
                break

        return details

    def _scrape_category(self, category: str) -> List[Dict[str, Any]]:
        """Scrape tools from a specific category."""
        if not self.driver:
            return []

        category_url = f"{FuturepediaConfig.BASE_URL}/ai-tools/{category}"
        self.logger.info(f"Scraping category: {category} from {category_url}")

        tools: List[Dict[str, Any]] = []

        try:
            self.rate_limiter.wait()
            self.driver.get(category_url)

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)

            scroll_attempts = 0
            max_scroll_attempts = 10
            last_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )

            while (
                len(tools) < self.limit_per_category
                and scroll_attempts < max_scroll_attempts
            ):
                new_tools = self._extract_tools_from_page(category)

                for tool in new_tools:
                    url = tool.get("futurepedia_url", "")
                    if url and not any(t.get("futurepedia_url") == url for t in tools):
                        tools.append(tool)

                        if len(tools) >= self.limit_per_category:
                            break

                if len(tools) >= self.limit_per_category:
                    break

                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(2)

                new_height = self.driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    scroll_attempts += 1
                    if scroll_attempts >= 3:
                        break
                else:
                    scroll_attempts = 0
                    last_height = new_height

        except Exception as e:
            self.logger.error(f"Error scraping category {category}: {e}")

        self.logger.info(f"Collected {len(tools)} tools from category: {category}")
        return tools[: self.limit_per_category]

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Execute the scraping process across all categories.

        Returns:
            List of normalized tool items
        """
        self.logger.info(
            f"Starting Futurepedia scrape (categories={len(self.categories)}, "
            f"limit_per_category={self.limit_per_category})"
        )

        try:
            self._init_driver()

            all_tools: List[Dict[str, Any]] = []

            for category in self.categories:
                tools = self._scrape_category(category)
                all_tools.extend(tools)

            self.logger.info(f"Total tools collected: {len(all_tools)}")

            for i, tool in enumerate(all_tools):
                tool_name = tool.get("tool_name", "unknown")
                self.logger.info(
                    f"Fetching details for {tool_name} ({i+1}/{len(all_tools)})"
                )

                details = self._get_tool_details(tool.get("futurepedia_url", ""))
                tool.update(details)

                normalized = normalize_item(
                    title=tool.get("tool_name", ""),
                    description=tool.get("long_description")
                    or tool.get("short_description", ""),
                    url=tool.get("futurepedia_url", ""),
                    external_url=tool.get("website_url", ""),
                    category=tool.get("primary_category", ""),
                    tags=tool.get("tags", []) + tool.get("subcategories", []),
                    metrics={
                        "rating": tool.get("rating", 0),
                        "views": tool.get("views", 0),
                        "verified": tool.get("verified_status", False),
                        "pricing": tool.get("pricing", {}),
                    },
                    images=(
                        [tool.get("thumbnail_image")]
                        if tool.get("thumbnail_image")
                        else []
                    ),
                    raw=tool,
                )
                self.output_writer.add_item(normalized)

            self.logger.info(
                f"Scraping complete. Total items: {self.output_writer.count}"
            )
            return self.output_writer.items

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}", exc_info=True)
            raise

        finally:
            self._close_driver()

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
    """CLI entry point for Futurepedia scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape AI tools from Futurepedia")
    default_limit = FuturepediaConfig.DEFAULT_LIMIT_PER_CATEGORY
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help=f"Max items per category (default: {default_limit})",
    )
    parser.add_argument(
        "--categories",
        type=str,
        help="Comma-separated list of categories to scrape",
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
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window",
    )

    args = parser.parse_args()

    headless = not args.no_headless
    categories = None
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]

    scraper = FuturepediaScraper(
        headless=headless,
        limit_per_category=args.limit,
        categories=categories,
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
