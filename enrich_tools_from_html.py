#!/usr/bin/env python3
"""
Script to enrich existing tools in the database with data from scraped HTML files.
This script parses HTML files from the raw_html directory and updates tools
that are missing short_description, tags, or other fields.
"""

import os
import re
import sys
from pathlib import Path

# Django setup - must happen before importing models
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "one9founders.settings")

import django  # noqa: E402

try:
    django.setup()
except Exception:
    print("Django setup failed")
    sys.exit(1)

from bs4 import BeautifulSoup  # noqa: E402
from django.db import models  # noqa: E402
from django.utils.text import slugify  # noqa: E402

from api.models import Tool  # noqa: E402


def parse_tool_html(filepath):
    """Parse a single HTML file and extract tool data."""
    try:
        with open(filepath, "r", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
    except Exception:
        return None

    data = {}

    # Name
    name_elem = soup.find("h1")
    data["name"] = name_elem.text.strip() if name_elem else None

    # Short description (tagline)
    tagline = soup.find("div", class_="tagline")
    data["short_description"] = tagline.text.strip()[:200] if tagline else None

    # Full description
    desc = soup.find("div", class_="ai_description")
    if desc:
        text = desc.get_text(separator=" ", strip=True)
        if text.startswith("Overview"):
            text = text[8:].strip()
        data["description"] = text
    else:
        data["description"] = None

    # Website
    website = soup.find("a", class_="ai_top_link")
    if website and website.get("href"):
        href = website.get("href")
        # Clean up referral params
        if "?" in href:
            href = href.split("?")[0]
        data["website"] = href
    else:
        data["website"] = None

    # Look for pricing info
    pricing_text = ""
    for div in soup.find_all("div"):
        classes = div.get("class", [])
        if any("pricing" in c.lower() for c in classes):
            pricing_text += " " + div.get_text(strip=True)

    # Determine pricing model
    pricing_text_lower = pricing_text.lower()
    if "free" in pricing_text_lower and "paid" in pricing_text_lower:
        data["pricing_models"] = ["freemium"]
        data["free_tier_available"] = True
    elif "free" in pricing_text_lower:
        data["pricing_models"] = ["free"]
        data["free_tier_available"] = True
    elif "paid" in pricing_text_lower:
        data["pricing_models"] = ["paid"]
        data["free_tier_available"] = False
    else:
        data["pricing_models"] = []
        data["free_tier_available"] = None

    # Extract pricing amount
    price_match = re.search(r"\$(\d+(?:\.\d{2})?)", pricing_text)
    if price_match:
        try:
            data["pricing_from"] = float(price_match.group(1))
        except ValueError:
            data["pricing_from"] = None
    else:
        data["pricing_from"] = None

    # Generate slug from filename
    filename = os.path.basename(filepath)
    data["slug"] = filename.replace(".html", "")

    return data


def enrich_tool(tool, html_data):
    """Update a tool with data from HTML if fields are missing."""
    updated_fields = []

    # Update short_description if missing
    if not tool.short_description and html_data.get("short_description"):
        tool.short_description = html_data["short_description"][:200]
        updated_fields.append("short_description")

    # Update description if missing or very short
    if html_data.get("description"):
        if not tool.description or len(tool.description) < 50:
            tool.description = html_data["description"]
            updated_fields.append("description")

    # Update website if missing
    if not tool.website and html_data.get("website"):
        tool.website = html_data["website"]
        updated_fields.append("website")

    # Update pricing_models if empty
    if not tool.pricing_models and html_data.get("pricing_models"):
        tool.pricing_models = html_data["pricing_models"]
        updated_fields.append("pricing_models")

    # Update free_tier_available if not set
    if html_data.get("free_tier_available") is not None:
        if not tool.free_tier_available and html_data["free_tier_available"]:
            tool.free_tier_available = html_data["free_tier_available"]
            updated_fields.append("free_tier_available")

    # Update pricing_from if missing
    if tool.pricing_from is None and html_data.get("pricing_from"):
        tool.pricing_from = html_data["pricing_from"]
        updated_fields.append("pricing_from")

    return updated_fields


def main():
    html_dir = Path("/home/ubuntu/html_data/raw_html")

    if not html_dir.exists():
        print(f"HTML directory not found: {html_dir}")
        sys.exit(1)

    html_files = list(html_dir.glob("*.html"))
    print(f"Found {len(html_files)} HTML files")

    # Build a mapping of slug -> HTML data
    print("Parsing HTML files...")
    html_data_by_slug = {}
    html_data_by_name = {}

    for i, filepath in enumerate(html_files):
        if i % 1000 == 0:
            print(f"  Parsed {i}/{len(html_files)} files...")

        data = parse_tool_html(filepath)
        if data and data.get("name"):
            slug = data["slug"]
            name = data["name"]
            html_data_by_slug[slug] = data
            # Also index by normalized name for fuzzy matching
            normalized_name = slugify(name)
            html_data_by_name[normalized_name] = data

    print(f"Successfully parsed {len(html_data_by_slug)} tools from HTML")

    # Get all tools that need enrichment
    tools_to_update = Tool.objects.filter(
        models.Q(short_description="")
        | models.Q(short_description__isnull=True)
        | models.Q(pricing_models=[])
    )

    print(f"Found {tools_to_update.count()} tools that may need enrichment")

    updated_count = 0
    matched_count = 0

    for tool in tools_to_update.iterator():
        # Try to match by slug first
        html_data = html_data_by_slug.get(tool.slug)

        # If not found, try by normalized name
        if not html_data:
            normalized_name = slugify(tool.name)
            html_data = html_data_by_name.get(normalized_name)

        if html_data:
            matched_count += 1
            updated_fields = enrich_tool(tool, html_data)

            if updated_fields:
                # Save without triggering embedding regeneration
                tool.save(update_fields=updated_fields)
                updated_count += 1

                if updated_count % 100 == 0:
                    print(f"  Updated {updated_count} tools...")

    print("\nSummary:")
    print(f"  Matched {matched_count} tools with HTML data")
    print(f"  Updated {updated_count} tools with new data")


if __name__ == "__main__":
    main()
