import requests
from bs4 import BeautifulSoup
import time
import logging
import urllib.parse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; One9FoundersBot/1.0 +https://one9founders.com)"
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    if '<' in text:
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(strip=True)
    return text.strip()


def is_meaningful(text: str, min_length: int = 30) -> bool:
    """Check if text is worth analysing."""
    if not text or len(text.strip()) < min_length:
        return False
    # Skip if it is just a URL
    if text.strip().startswith('http'):
        return False
    # Skip if less than 4 words
    if len(text.strip().split()) < 4:
        return False
    return True


def deduplicate(mentions: list) -> list:
    """Remove duplicate mentions based on first 100 characters."""
    seen = set()
    unique = []
    for m in mentions:
        key = m['text'][:100].lower()
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


# ── Reddit ─────────────────────────────────────────────────────────────────────

def fetch_reddit_mentions(tool_name: str) -> list:
    """
    Fetch Reddit mentions using public JSON API.
    Tries multiple search queries for better coverage.
    Falls back gracefully if blocked.
    """
    mentions = []
    encoded = urllib.parse.quote(tool_name)

    queries = [
        f"{encoded}+review",
        f"{encoded}+experience",
        f"{encoded}+alternative"
    ]

    for query in queries:
        url = f"https://www.reddit.com/search.json?q={query}&sort=top&limit=10&type=link"
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()

            for post in data['data']['children']:
                d = post['data']
                title = d.get('title', '')
                body = d.get('selftext', '')
                subreddit = d.get('subreddit', '')
                score = d.get('score', 0)
                combined = f"{title}. {body}".strip()

                if is_meaningful(combined) and score >= 1:
                    mentions.append({
                        "source": f"reddit.com/r/{subreddit}",
                        "text": combined[:600],
                        "score": score
                    })

            time.sleep(0.5)

        except requests.Timeout:
            logger.warning(f"Reddit timeout for: {query}")
        except Exception as e:
            logger.error(f"Reddit scrape failed for {tool_name}: {e}")
            break  # If first query is blocked, skip remaining

    unique = deduplicate(mentions)
    logger.info(f"Reddit: found {len(unique)} mentions for {tool_name}")
    return unique[:15]


# ── Product Hunt ───────────────────────────────────────────────────────────────

def fetch_producthunt_mentions(tool_name: str) -> list:
    """
    Fetch Product Hunt search results.
    ProductHunt is JavaScript rendered so we get limited data.
    But taglines and descriptions are still useful.
    """
    mentions = []
    encoded = tool_name.replace(' ', '+')
    url = f"https://www.producthunt.com/search?q={encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract all paragraph text
        for tag in soup.find_all(['p', 'h3', 'h2']):
            text = tag.get_text(strip=True)
            if is_meaningful(text, min_length=40) and len(text) < 800:
                mentions.append({
                    "source": "producthunt.com",
                    "text": text[:400]
                })

        # Extract meta description which often has good summary
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta and meta.get('content'):
            text = meta['content']
            if is_meaningful(text):
                mentions.append({
                    "source": "producthunt.com",
                    "text": text[:400]
                })

    except requests.Timeout:
        logger.warning(f"ProductHunt timeout for {tool_name}")
    except Exception as e:
        logger.error(f"ProductHunt scrape failed for {tool_name}: {e}")

    unique = deduplicate(mentions)
    logger.info(f"ProductHunt: found {len(unique)} mentions for {tool_name}")
    return unique[:10]


# ── Hacker News ────────────────────────────────────────────────────────────────

def fetch_hackernews_mentions(tool_name: str) -> list:
    """
    Fetch Hacker News discussions mentioning a tool.
    Completely free. No API key needed.
    IMPORTANT: Do NOT use tags filter. it returns 0 results.
    Just use query without tags for best results.
    """
    mentions = []
    encoded = urllib.parse.quote(tool_name)

    # Two passes. recent and relevant
    urls = [
        f"https://hn.algolia.com/api/v1/search?query={encoded}&hitsPerPage=15",
        f"https://hn.algolia.com/api/v1/search_by_date?query={encoded}&hitsPerPage=10"
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()

            for hit in data.get('hits', []):
                text = hit.get('comment_text') or hit.get('title') or ''
                text = clean_html(text)
                if is_meaningful(text):
                    mentions.append({
                        "source": "news.ycombinator.com",
                        "text": text[:600]
                    })

            time.sleep(0.3)

        except requests.Timeout:
            logger.warning(f"HackerNews timeout for {tool_name}")
        except Exception as e:
            logger.error(f"HackerNews scrape failed for {tool_name}: {e}")

    unique = deduplicate(mentions)
    logger.info(f"HackerNews: found {len(unique)} mentions for {tool_name}")
    return unique[:15]


# ── YouTube ────────────────────────────────────────────────────────────────────

def fetch_youtube_mentions(tool_name: str) -> list:
    """
    Fetch YouTube video titles about a tool.
    Especially useful for India-specific content.
    Extracts video titles from page source without API key.
    """
    mentions = []
    encoded = urllib.parse.quote(f"{tool_name} review")
    url = f"https://www.youtube.com/results?search_query={encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        # YouTube embeds data in script tags as JSON
        # Extract video title snippets
        text = response.text
        tool_lower = tool_name.lower()
        position = 0

        while True:
            pos = text.lower().find(tool_lower, position)
            if pos == -1 or len(mentions) >= 5:
                break
            snippet = text[max(0, pos - 20):pos + 200]
            snippet = snippet.replace('\\n', ' ').replace('\\"', '"').replace('\\u0026', '&')
            snippet = clean_html(snippet)
            if is_meaningful(snippet, min_length=20):
                mentions.append({
                    "source": "youtube.com",
                    "text": snippet[:300]
                })
            position = pos + 100

    except requests.Timeout:
        logger.warning(f"YouTube timeout for {tool_name}")
    except Exception as e:
        logger.error(f"YouTube scrape failed for {tool_name}: {e}")

    unique = deduplicate(mentions)
    logger.info(f"YouTube: found {len(unique)} mentions for {tool_name}")
    return unique[:5]


# ── Trustpilot ─────────────────────────────────────────────────────────────────

def fetch_trustpilot_mentions(tool_name: str) -> list:
    """
    Fetch Trustpilot reviews.
    Works for tools with consumer-facing products.
    """
    mentions = []
    encoded = urllib.parse.quote(tool_name)
    url = f"https://www.trustpilot.com/search?query={encoded}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Try multiple selectors since Trustpilot changes its HTML often
        for tag in soup.find_all(['p', 'span', 'div']):
            text = tag.get_text(strip=True)
            if is_meaningful(text, min_length=50) and len(text) < 600:
                mentions.append({
                    "source": "trustpilot.com",
                    "text": text[:400]
                })
            if len(mentions) >= 10:
                break

    except requests.Timeout:
        logger.warning(f"Trustpilot timeout for {tool_name}")
    except Exception as e:
        logger.error(f"Trustpilot scrape failed for {tool_name}: {e}")

    unique = deduplicate(mentions)
    logger.info(f"Trustpilot: found {len(unique)} mentions for {tool_name}")
    return unique[:8]


# ── G2 Crowd ───────────────────────────────────────────────────────────────────

def fetch_g2_mentions(tool_name: str) -> list:
    """
    Fetch G2 review snippets.
    G2 has verified business reviews. very high trust signal.
    """
    mentions = []
    encoded = tool_name.replace(' ', '-').lower()
    url = f"https://www.g2.com/search?query={urllib.parse.quote(tool_name)}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup.find_all(['p', 'span']):
            text = tag.get_text(strip=True)
            if is_meaningful(text, min_length=40) and len(text) < 600:
                mentions.append({
                    "source": "g2.com",
                    "text": text[:400]
                })
            if len(mentions) >= 8:
                break

    except requests.Timeout:
        logger.warning(f"G2 timeout for {tool_name}")
    except Exception as e:
        logger.error(f"G2 scrape failed for {tool_name}: {e}")

    unique = deduplicate(mentions)
    logger.info(f"G2: found {len(unique)} mentions for {tool_name}")
    return unique[:8]


# ── Master Gatherer ─────────────────────────────────────────────────────────────

def gather_all_mentions(tool_name: str) -> list:
    """
    Master function that collects mentions from all sources.
    Automation calls this. Agent receives the combined output.

    Sources in priority order:
    1. Hacker News. free, high quality, working confirmed
    2. Reddit. best depth when not blocked
    3. Product Hunt. most targeted for AI tools
    4. G2. verified business reviews
    5. YouTube. India-specific high volume
    6. Trustpilot. consumer volume
    """
    all_mentions = []

    # Source 1. Hacker News first since confirmed working
    hn = fetch_hackernews_mentions(tool_name)
    all_mentions.extend(hn)
    time.sleep(0.5)

    # Source 2. Reddit
    reddit = fetch_reddit_mentions(tool_name)
    all_mentions.extend(reddit)
    time.sleep(0.5)

    # Source 3. Product Hunt
    ph = fetch_producthunt_mentions(tool_name)
    all_mentions.extend(ph)
    time.sleep(0.5)

    # Source 4. G2
    g2 = fetch_g2_mentions(tool_name)
    all_mentions.extend(g2)
    time.sleep(0.5)

    # Source 5. YouTube
    yt = fetch_youtube_mentions(tool_name)
    all_mentions.extend(yt)
    time.sleep(0.5)

    # Source 6. Trustpilot
    tp = fetch_trustpilot_mentions(tool_name)
    all_mentions.extend(tp)

    # Final deduplication across all sources
    final = deduplicate(all_mentions)
    total = len(final)

    logger.info(
        f"Total mentions for {tool_name}: {total} "
        f"(HN:{len(hn)} Reddit:{len(reddit)} PH:{len(ph)} "
        f"G2:{len(g2)} YT:{len(yt)} TP:{len(tp)})"
    )

    return final