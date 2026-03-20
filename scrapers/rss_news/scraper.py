import sys
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import feedparser
from bs4 import BeautifulSoup

# Add the project root to sys.path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.logger import setup_logging
from utils.output import OutputWriter, normalize_item

# RSS Feeds to scrape
RSS_SOURCES = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "VentureBeat": "https://venturebeat.com/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "OpenAI Blog": "https://openai.com/blog/rss.xml",
    "Anthropic Blog": "https://www.anthropic.com/rss.xml",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "Google AI Blog": "https://blog.google/technology/ai/rss/",
}

class RSSNewsScraper:
    """Scraper for fetching and normalizing news from RSS feeds."""

    def __init__(
        self,
        limit_per_source: int = 10,
        output_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize the RSS scraper.

        Args:
            limit_per_source: Max items to fetch per RSS feed.
            output_dir: Directory for output files.
        """
        self.limit_per_source = limit_per_source
        self.output_dir = output_dir
        self.logger = setup_logging("rss_news", Path("logs") if not output_dir else output_dir / "logs")
        self.output_writer = OutputWriter("RSSNews", self.output_dir)

    def extract_image(self, entry: Any) -> str:
        """
        Extract the best possible image URL from an RSS entry.
        
        Args:
            entry: A feedparser entry object.
            
        Returns:
            Image URL or empty string.
        """
        # 1. Check media:content (most standard)
        if 'media_content' in entry and entry.media_content:
            for media in entry.media_content:
                if 'image' in media.get('type', '') or media.get('medium') == 'image':
                    return media.get('url', '')
            return entry.media_content[0].get('url', '')

        # 2. Check media:thumbnail
        if 'media_thumbnail' in entry and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url', '')

        # 3. Check links for image types
        if 'links' in entry:
            for link in entry.links:
                if 'image' in link.get('type', ''):
                    return link.get('href', '')

        # 4. Fallback: Parse summary/description for <img> tags
        html_content = entry.get("summary") or entry.get("description", "")
        if html_content:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                img = soup.find('img')
                if img and img.get('src'):
                    return img['src']
            except Exception as e:
                self.logger.debug(f"BeautifulSoup parsing error: {e}")

        # 5. Check 'content' field if available
        if 'content' in entry and entry.content:
            content_html = entry.content[0].get('value', '')
            try:
                soup = BeautifulSoup(content_html, 'html.parser')
                img = soup.find('img')
                if img and img.get('src'):
                    return img['src']
            except Exception as e:
                self.logger.debug(f"BeautifulSoup content parsing error: {e}")

        return ""

    def parse_date(self, entry: Any) -> str:
        """
        Parse the publication date from an RSS entry reliably.
        
        Args:
            entry: A feedparser entry object.
            
        Returns:
            ISO format date string.
        """
        # Use published_parsed if available (it's a time.struct_time)
        struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
        
        if struct_time:
            try:
                # Convert struct_time to datetime (always UTC/naive in feedparser)
                dt = datetime.fromtimestamp(time.mktime(struct_time), tz=timezone.utc)
                return dt.isoformat()
            except (ValueError, OverflowError, TypeError):
                pass
        
        # Fallback to string parsing or current time
        published_str = entry.get("published") or entry.get("updated")
        if published_str:
            return published_str
            
        return datetime.now(timezone.utc).isoformat()

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Execute the scraping process for all RSS sources.

        Returns:
            List of normalized news items.
        """
        self.logger.info(f"Starting RSS News scrape (limit_per_source={self.limit_per_source})")

        total_items = 0
        for source_name, url in RSS_SOURCES.items():
            self.logger.info(f"Fetching RSS feed from {source_name}: {url}")
            try:
                feed = feedparser.parse(url)
                
                if feed.bozo:
                    self.logger.warning(f"Possible issue with {source_name} feed: {feed.bozo_exception}")

                entries = feed.entries[:self.limit_per_source]
                self.logger.info(f"Found {len(entries)} entries for {source_name}")

                for entry in entries:
                    # Extract date information (production fix)
                    published = self.parse_date(entry)
                    
                    # Extract image information (production fix)
                    image_url = self.extract_image(entry)
                    
                    # Clean the description (remove HTML tags for metrics/preview)
                    summary_html = entry.get("summary") or entry.get("description", "")
                    clean_description = BeautifulSoup(summary_html, 'html.parser').get_text(separator=' ').strip()
                    
                    normalized = normalize_item(
                        title=entry.get("title", ""),
                        description=clean_description or entry.get("title", ""),
                        url=entry.get("link", ""),
                        external_url=entry.get("link", ""),
                        category="AI News",
                        tags=["ai", "news", source_name.lower().replace(" ", "-")],
                        metrics={
                            "source_label": source_name,
                            "published": published,
                            "original_summary": summary_html[:500] # Keep a bit of HTML for debugging
                        },
                        images=[image_url] if image_url else [],
                        raw=dict(entry),
                    )
                    self.output_writer.add_item(normalized)
                    total_items += 1

            except Exception as e:
                self.logger.error(f"Error scraping {source_name}: {e}")
                continue

        self.logger.info(f"RSS scraping complete. Total items: {total_items}")
        return self.output_writer.items

    def save_output(self, output_path: Optional[Path] = None) -> Path:
        """Save the scraped data to a JSON file."""
        if output_path:
            return self.output_writer.write_to_path(output_path)
        return self.output_writer.write()

def main() -> None:
    """CLI entry point for RSS News scraper."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape AI news from RSS feeds")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max items to scrape per source (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path",
    )

    args = parser.parse_args()

    scraper = RSSNewsScraper(limit_per_source=args.limit)

    try:
        items = scraper.scrape()
        
        if args.output:
            saved_path = scraper.save_output(Path(args.output))
        else:
            saved_path = scraper.save_output()

        print(f"\n--- RSS Scrape Summary ---")
        print(f"Total items scraped: {len(items)}")
        print(f"Output saved to: {saved_path}")
        
        # Display first 3 items for verification
        for i, item in enumerate(items[:3]):
            print(f"\n[{i+1}] {item['title']}")
            print(f"    Source: {item['metrics']['source_label']}")
            print(f"    Date: {item['metrics']['published']}")
            print(f"    Image: {item['images'][0] if item['images'] else 'None'}")
            print(f"    Link: {item['url']}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
