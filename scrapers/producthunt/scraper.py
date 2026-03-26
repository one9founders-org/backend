"""
Product Hunt AI Launches Scraper.
Scrapes AI-related product launches from Product Hunt.
Uses web scraping with improved selectors for the current site structure.
"""

import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.scraper_settings import ProductHuntConfig  # noqa: E402
from utils.logger import ScraperLogger, setup_logging  # noqa: E402
from utils.output import OutputWriter, normalize_item  # noqa: E402
from utils.rate_limiter import RateLimiter  # noqa: E402
from utils.retry import RetryContext  # noqa: E402
from utils.selenium_driver import create_driver  # noqa: E402


class ProductHuntScraper:
    """Scraper for Product Hunt AI launches."""

    def __init__(
        self,
        headless: bool = True,
        days_back: int = ProductHuntConfig.DEFAULT_DAYS_BACK,
        limit: int = ProductHuntConfig.DEFAULT_LIMIT,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize Product Hunt scraper.

        Args:
            headless: Run browser in headless mode
            days_back: Number of days back to scrape
            limit: Maximum number of items to scrape
            output_dir: Directory for output files
        """
        self.headless = headless
        self.days_back = days_back
        self.limit = limit
        self.output_dir = output_dir or ProductHuntConfig.OUTPUT_DIR

        self.logger: ScraperLogger = setup_logging(
            "producthunt", ProductHuntConfig.LOG_DIR
        )
        self.rate_limiter = RateLimiter()
        self.driver: Optional[WebDriver] = None
        self.output_writer = OutputWriter("ProductHunt", self.output_dir)

        self.cutoff_date = datetime.utcnow() - timedelta(days=days_back)

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

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string from Product Hunt."""
        if not date_str:
            return None

        date_str = date_str.strip().lower()

        if "today" in date_str:
            return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        elif "yesterday" in date_str:
            return (datetime.utcnow() - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        days_match = re.search(r"(\d+)\s*days?\s*ago", date_str)
        if days_match:
            days = int(days_match.group(1))
            return (datetime.utcnow() - timedelta(days=days)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        date_formats = [
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%d",
            "%d %B %Y",
            "%d %b %Y",
        ]
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _extract_products_from_page(self) -> List[Dict[str, Any]]:
        """Extract product information from the current page."""
        if not self.driver:
            return []

        products: List[Dict[str, Any]] = []
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        product_links = soup.find_all("a", href=re.compile(r"/posts/[^/]+$"))

        seen_urls: set = set()

        for link in product_links:
            try:
                href = link.get("href", "")
                if not href or href in seen_urls:
                    continue

                product_url = (
                    f"{ProductHuntConfig.BASE_URL}{href}"
                    if href.startswith("/")
                    else href
                )
                seen_urls.add(href)

                parent = link.find_parent("div")
                if not parent:
                    parent = link

                name_elem = link.find(["h2", "h3", "strong"])
                if not name_elem:
                    name_elem = link.find(string=True, recursive=False)

                product_name = ""
                if name_elem:
                    if hasattr(name_elem, "get_text"):
                        product_name = name_elem.get_text(strip=True)
                    else:
                        product_name = str(name_elem).strip()

                if not product_name or len(product_name) < 2:
                    slug = href.split("/posts/")[-1] if "/posts/" in href else ""
                    product_name = slug.replace("-", " ").title()

                if not product_name:
                    continue

                tagline = ""
                desc_elem = parent.find("p")
                if desc_elem:
                    tagline = desc_elem.get_text(strip=True)

                upvotes = 0
                vote_patterns = [
                    r"(\d+)\s*upvote",
                    r"(\d+)\s*vote",
                    r"▲\s*(\d+)",
                ]
                parent_text = parent.get_text()
                for pattern in vote_patterns:
                    match = re.search(pattern, parent_text, re.IGNORECASE)
                    if match:
                        upvotes = int(match.group(1))
                        break

                button_elem = parent.find("button")
                if button_elem and upvotes == 0:
                    button_text = button_elem.get_text(strip=True)
                    num_match = re.search(r"(\d+)", button_text)
                    if num_match:
                        upvotes = int(num_match.group(1))

                img_elem = parent.find("img")
                thumbnail = ""
                if img_elem:
                    thumbnail = img_elem.get("src", "") or img_elem.get("data-src", "")

                products.append(
                    {
                        "product_name": product_name,
                        "tagline": tagline,
                        "producthunt_url": product_url,
                        "upvotes": upvotes,
                        "thumbnail_image": thumbnail,
                        "topics": ["artificial-intelligence"],
                    }
                )

            except Exception as e:
                self.logger.warning(f"Error extracting product: {e}")
                continue

        return products

    def _get_product_details(self, product_url: str) -> Dict[str, Any]:
        """Fetch additional details from the product page."""
        details: Dict[str, Any] = {
            "full_description": "",
            "website_url": "",
            "makers": [],
            "launch_date": None,
            "comments": 0,
        }

        if not product_url or not self.driver:
            return details

        retry_ctx = RetryContext(max_retries=2)

        while True:
            try:
                self.rate_limiter.wait()
                self.driver.get(product_url)

                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2)

                soup = BeautifulSoup(self.driver.page_source, "html.parser")

                desc_elems = soup.find_all("p")
                for desc in desc_elems:
                    text = desc.get_text(strip=True)
                    if len(text) > 50:
                        details["full_description"] = text
                        break

                external_links = soup.find_all("a", href=re.compile(r"^https?://"))
                for link in external_links:
                    href = link.get("href", "")
                    if "producthunt.com" not in href and "twitter.com" not in href:
                        if "ref=producthunt" in href or link.get("rel") == ["nofollow"]:
                            details["website_url"] = href
                            break

                comment_match = re.search(
                    r"(\d+)\s*comment", soup.get_text(), re.IGNORECASE
                )
                if comment_match:
                    details["comments"] = int(comment_match.group(1))

                break

            except (TimeoutException, WebDriverException) as e:
                if retry_ctx.should_retry(e):
                    self.logger.warning(
                        f"Retrying details: {e} (attempt {retry_ctx.attempt})"
                    )
                    continue
                else:
                    self.logger.error(f"Failed to fetch product details: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Unexpected error fetching product details: {e}")
                break

        return details

    def _scroll_and_collect(self) -> List[Dict[str, Any]]:
        """Scroll through the page and collect products."""
        if not self.driver:
            return []

        all_products: List[Dict[str, Any]] = []
        seen_urls: set = set()
        scroll_attempts = 0
        max_scroll_attempts = 20

        while len(all_products) < self.limit and scroll_attempts < max_scroll_attempts:
            products = self._extract_products_from_page()

            for product in products:
                url = product.get("producthunt_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_products.append(product)

                    if len(all_products) >= self.limit:
                        break

            if len(all_products) >= self.limit:
                break

            last_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(3)

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= 3:
                    break
            else:
                scroll_attempts = 0

        self.logger.info(f"Collected {len(all_products)} products from listing")
        return all_products[: self.limit]

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Execute the scraping process.

        Returns:
            List of normalized product items
        """
        self.logger.info(
            f"Starting Product Hunt scrape "
            f"(days_back={self.days_back}, limit={self.limit})"
        )

        try:
            self._init_driver()

            self.rate_limiter.wait()
            self.driver.get(ProductHuntConfig.AI_TOPICS_URL)

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)
            self.logger.info("Loaded AI topics page")

            products = self._scroll_and_collect()

            for i, product in enumerate(products):
                if i >= self.limit:
                    break

                self.logger.info(
                    f"Fetching details for {product.get('product_name')} "
                    f"({i+1}/{len(products)})"
                )

                details = self._get_product_details(product.get("producthunt_url", ""))
                product.update(details)

                normalized = normalize_item(
                    title=product.get("product_name", ""),
                    description=product.get("full_description")
                    or product.get("tagline", ""),
                    url=product.get("producthunt_url", ""),
                    external_url=product.get("website_url", ""),
                    category="artificial-intelligence",
                    tags=product.get("topics", []),
                    metrics={
                        "upvotes": product.get("upvotes", 0),
                        "comments": product.get("comments", 0),
                    },
                    images=(
                        [product.get("thumbnail_image")]
                        if product.get("thumbnail_image")
                        else []
                    ),
                    raw=product,
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
    """CLI entry point for Product Hunt scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape AI launches from Product Hunt")
    parser.add_argument(
        "--limit",
        type=int,
        default=ProductHuntConfig.DEFAULT_LIMIT,
        help=f"Max items to scrape (default: {ProductHuntConfig.DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=ProductHuntConfig.DEFAULT_DAYS_BACK,
        help=f"Days back to scrape (default: {ProductHuntConfig.DEFAULT_DAYS_BACK})",
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

    scraper = ProductHuntScraper(
        headless=headless,
        days_back=args.days_back,
        limit=args.limit,
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
