"""Unit tests for the GitHub most-starred OSS tools scraper."""

from unittest.mock import patch

from scrapers.github.scraper import GitHubStarredScraper


def test_scraper_merges_star_hits_and_seeds_sorted_by_stars():
    scraper = GitHubStarredScraper(limit=10, min_stars=50, token="test")
    starred = {
        "html_url": "https://github.com/acme/hot-tool",
        "full_name": "acme/hot-tool",
        "description": "Popular OSS tool",
        "stargazers_count": 8000,
        "forks_count": 100,
        "fork": False,
        "archived": False,
        "topics": ["llm-tools"],
        "license": {"spdx_id": "MIT"},
        "homepage": "https://hot-tool.example",
        "pushed_at": "2026-09-01T00:00:00Z",
    }
    seed = {
        "html_url": "https://github.com/reticlehq/reticle",
        "full_name": "reticlehq/reticle",
        "description": "Verify running web apps",
        "stargazers_count": 42,
        "forks_count": 3,
        "fork": False,
        "archived": False,
        "topics": ["devtools"],
        "license": {"spdx_id": "Apache-2.0"},
        "homepage": "https://www.reticle.sh",
        "pushed_at": "2026-09-10T00:00:00Z",
    }

    with (
        patch.object(scraper, "_search", return_value=[starred]) as search,
        patch.object(
            scraper,
            "_repo",
            side_effect=lambda name: seed if name == "reticlehq/reticle" else None,
        ),
    ):
        items = scraper.scrape()

    assert search.call_count >= 1
    urls = {item["url"] for item in items}
    assert "https://github.com/acme/hot-tool" in urls
    assert "https://github.com/reticlehq/reticle" in urls
    assert items[0]["url"] == "https://github.com/acme/hot-tool"
    assert items[0]["title"] == "github/acme/hot-tool"
    assert items[0]["metrics"]["stars"] == 8000


def test_scraper_skips_forks_and_low_star_non_seeds():
    scraper = GitHubStarredScraper(limit=10, min_stars=100, token="test")
    assert (
        scraper._normalize(
            {
                "html_url": "https://github.com/acme/fork",
                "full_name": "acme/fork",
                "fork": True,
                "stargazers_count": 9999,
            }
        )
        is None
    )
    assert (
        scraper._normalize(
            {
                "html_url": "https://github.com/acme/tiny",
                "full_name": "acme/tiny",
                "fork": False,
                "archived": False,
                "stargazers_count": 10,
            }
        )
        is None
    )
    # Seeds are allowed below min_stars.
    row = scraper._normalize(
        {
            "html_url": "https://github.com/reticlehq/reticle",
            "full_name": "reticlehq/reticle",
            "fork": False,
            "archived": False,
            "stargazers_count": 10,
            "description": "Reticle",
            "topics": [],
        }
    )
    assert row is not None
    assert row["title"] == "github/reticlehq/reticle"
