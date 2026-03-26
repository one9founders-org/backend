"""
There's An AI For That (TAAFT) Scraper.
Scrapes newly added AI tools from theresanaiforthat.com.
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.scraper_settings import TAAFTConfig  # noqa: E402
from utils.logger import ScraperLogger, setup_logging  # noqa: E402
from utils.output import OutputWriter, normalize_item  # noqa: E402
from utils.rate_limiter import RateLimiter  # noqa: E402
from utils.retry import RetryContext  # noqa: E402
from utils.selenium_driver import create_driver  # noqa: E402


class TAAFTScraper:
    """Scraper for There's An AI For That newly added tools."""

    def __init__(
        self,
        headless: bool = True,
        limit: int = TAAFTConfig.DEFAULT_LIMIT,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize TAAFT scraper.

        Args:
            headless: Run browser in headless mode
            limit: Maximum number of items to scrape
            output_dir: Directory for output files
        """
        self.headless = headless
        self.limit = limit
        self.output_dir = output_dir or TAAFTConfig.OUTPUT_DIR

        self.logger: ScraperLogger = setup_logging("taaft", TAAFTConfig.LOG_DIR)
        self.rate_limiter = RateLimiter()
        self.driver: Optional[WebDriver] = None
        self.output_writer = OutputWriter("TAAFT", self.output_dir)

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

    def _scroll_to_load(self, max_scrolls: Optional[int] = None) -> int:
        """
        Scroll down to load more content via infinite scroll.

        Args:
            max_scrolls: Maximum number of scroll attempts

        Returns:
            Number of scrolls performed
        """
        if not self.driver:
            return 0

        _max_scrolls = max_scrolls or TAAFTConfig.MAX_SCROLLS
        scroll_pause = TAAFTConfig.SCROLL_PAUSE_TIME
        scrolls = 0
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        while scrolls < _max_scrolls:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(scroll_pause)

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                time.sleep(scroll_pause)
                new_height = self.driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    break

            last_height = new_height
            scrolls += 1

            try:
                cards = self.driver.find_elements(
                    By.CSS_SELECTOR, 'a[href*="/ai/"], div[class*="tool"], article'
                )
                if len(cards) >= self.limit:
                    self.logger.info(f"Reached limit of {self.limit} items")
                    break
            except NoSuchElementException:
                pass

        self.logger.info(f"Performed {scrolls} scrolls")
        return scrolls

    def _extract_tool_card(self, card_element: Any) -> Optional[Dict[str, Any]]:
        """Extract tool information from a card element."""
        try:
            html = card_element.get_attribute("outerHTML")
            soup = BeautifulSoup(html, "html.parser")

            name_elem = soup.select_one(
                'h2, h3, [class*="title"], [class*="name"], strong'
            )
            tool_name = name_elem.get_text(strip=True) if name_elem else None

            if not tool_name:
                link = soup.select_one('a[href*="/ai/"]')
                if link:
                    href = link.get("href", "")
                    name_match = re.search(r"/ai/([^/]+)", href)
                    if name_match:
                        tool_name = name_match.group(1).replace("-", " ").title()

            if not tool_name:
                return None

            desc_elem = soup.select_one(
                'p, [class*="description"], [class*="desc"], [class*="tagline"]'
            )
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            link_elem = soup.select_one('a[href*="/ai/"]')
            tool_url = ""
            if link_elem and link_elem.get("href"):
                href = link_elem["href"]
                if href.startswith("/"):
                    tool_url = f"{TAAFTConfig.BASE_URL}{href}"
                else:
                    tool_url = href

            category_elems = soup.select(
                '[class*="category"], [class*="tag"], a[href*="/category/"]'
            )
            categories = []
            for cat in category_elems:
                cat_text = cat.get_text(strip=True)
                if cat_text and len(cat_text) < 50:
                    categories.append(cat_text)

            pricing_elem = soup.select_one(
                '[class*="pricing"], [class*="price"], [class*="free"]'
            )
            pricing_model = ""
            if pricing_elem:
                pricing_text = pricing_elem.get_text(strip=True).lower()
                if "free" in pricing_text:
                    pricing_model = "free"
                elif "paid" in pricing_text:
                    pricing_model = "paid"
                elif "freemium" in pricing_text:
                    pricing_model = "freemium"
                else:
                    pricing_model = pricing_text[:50]

            saves_elem = soup.select_one(
                '[class*="save"], [class*="bookmark"], [class*="heart"]'
            )
            saves_count = 0
            if saves_elem:
                saves_text = saves_elem.get_text(strip=True)
                saves_match = re.search(r"(\d+)", saves_text.replace(",", ""))
                if saves_match:
                    saves_count = int(saves_match.group(1))

            img_elem = soup.select_one("img[src], img[data-src]")
            thumbnail = ""
            if img_elem:
                thumbnail = img_elem.get("src") or img_elem.get("data-src", "")

            return {
                "tool_name": tool_name,
                "description": description,
                "taaft_url": tool_url,
                "categories": categories,
                "pricing_model": pricing_model,
                "saves_count": saves_count,
                "thumbnail_image": thumbnail,
            }

        except Exception as e:
            self.logger.warning(f"Error extracting tool card: {e}")
            return None

    def _get_tool_details(self, tool_url: str) -> Dict[str, Any]:
        """Fetch additional details from the tool page."""
        details: Dict[str, Any] = {
            "website_url": "",
            "features": [],
            "date_added": None,
            "full_description": "",
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

                soup = BeautifulSoup(self.driver.page_source, "html.parser")

                website_elem = soup.select_one(
                    'a[rel="nofollow"][target="_blank"], '
                    'a[href*="http"][class*="visit"], '
                    'a[href*="http"][class*="website"], '
                    'a[class*="external"]'
                )
                if website_elem and website_elem.get("href"):
                    href = website_elem["href"]
                    if "theresanaiforthat" not in href:
                        details["website_url"] = href

                desc_elem = soup.select_one(
                    '[class*="description"], '
                    "article p, "
                    "main p, "
                    '[class*="content"] p'
                )
                if desc_elem:
                    details["full_description"] = desc_elem.get_text(strip=True)

                feature_elems = soup.select(
                    '[class*="feature"] li, '
                    'ul[class*="feature"] li, '
                    '[class*="pros"] li'
                )
                features = []
                for feat in feature_elems[:10]:
                    feat_text = feat.get_text(strip=True)
                    if feat_text and len(feat_text) < 200:
                        features.append(feat_text)
                details["features"] = features

                date_elem = soup.select_one(
                    '[class*="date"], ' "time[datetime], " '[class*="added"]'
                )
                if date_elem:
                    date_str = date_elem.get("datetime") or date_elem.get_text(
                        strip=True
                    )
                    try:
                        for fmt in ["%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
                            try:
                                parsed = datetime.strptime(date_str.strip(), fmt)
                                details["date_added"] = parsed.isoformat()
                                break
                            except ValueError:
                                continue
                    except Exception as e:
                        self.logger.warning(
                            "Failed to parse date for tool: %s", e
                        )

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

    def _collect_tools(self) -> List[Dict[str, Any]]:
        """Collect tool cards from the page."""
        if not self.driver:
            return []

        tools: List[Dict[str, Any]] = []
        seen_urls: set = set()

        card_selectors = [
            'a[href*="/ai/"]',
            'div[class*="tool-card"]',
            'article[class*="tool"]',
            'div[class*="ai-tool"]',
            'li[class*="tool"]',
        ]

        for selector in card_selectors:
            try:
                cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    self.logger.info(
                        f"Found {len(cards)} cards with selector: {selector}"
                    )

                    for card in cards:
                        if len(tools) >= self.limit:
                            break

                        tool_data = self._extract_tool_card(card)
                        if tool_data and tool_data.get("taaft_url"):
                            url = tool_data["taaft_url"]
                            if url not in seen_urls:
                                seen_urls.add(url)
                                tools.append(tool_data)

                    if tools:
                        break
            except NoSuchElementException:
                continue

        self.logger.info(f"Collected {len(tools)} tools from listing")
        return tools

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Execute the scraping process.

        Returns:
            List of normalized tool items
        """
        self.logger.info(f"Starting TAAFT scrape (limit={self.limit})")

        try:
            self._init_driver()

            self.rate_limiter.wait()
            self.driver.get(TAAFTConfig.NEWLY_ADDED_URL)

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            self.logger.info("Loaded newly added page")

            self._scroll_to_load()

            tools = self._collect_tools()

            for i, tool in enumerate(tools):
                if i >= self.limit:
                    break

                self.logger.info(
                    f"Fetching details for {tool.get('tool_name')} ({i+1}/{len(tools)})"
                )

                details = self._get_tool_details(tool.get("taaft_url", ""))
                tool.update(details)

                normalized = normalize_item(
                    title=tool.get("tool_name", ""),
                    description=tool.get("full_description")
                    or tool.get("description", ""),
                    url=tool.get("taaft_url", ""),
                    external_url=tool.get("website_url", ""),
                    category=(
                        tool.get("categories", [""])[0]
                        if tool.get("categories")
                        else ""
                    ),
                    tags=tool.get("categories", []),
                    metrics={
                        "saves_count": tool.get("saves_count", 0),
                        "pricing_model": tool.get("pricing_model", ""),
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
    """CLI entry point for TAAFT scraper."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape newly added AI tools from There's An AI For That"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=TAAFTConfig.DEFAULT_LIMIT,
        help=f"Max items to scrape (default: {TAAFTConfig.DEFAULT_LIMIT})",
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

    scraper = TAAFTScraper(
        headless=headless,
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
