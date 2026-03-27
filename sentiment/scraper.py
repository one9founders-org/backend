import requests
from bs4 import BeautifulSoup
import time
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; One9FoundersBot/1.0 +https://one9founders.com)"
}

# ── Reddit ─────────────────────────────────────────────────────────────────────

def fetch_reddit_mentions(tool_name: str) -> list:
    """
    Fetch Reddit mentions using public JSON API.
    Searches across all subreddits for tool reviews and discussions.
    """
    mentions = []
    
    # Search across multiple relevant subreddits for better coverage
    queries = [
        f"{tool_name} review",
        f"{tool_name} experience",
        f"{tool_name} alternative"
    ]
    
    for query in queries:
        url = f"https://www.reddit.com/search.json?q={query}&sort=new&limit=10&type=link"
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
                
                combined = f"{title} {body}".strip()
                
                # Only include posts with some engagement
                if len(combined) > 30 and score > 0:
                    mentions.append({
                        "source": f"reddit.com/r/{subreddit}",
                        "text": combined[:600],
                        "score": score
                    })
            
            time.sleep(0.5)  # Respectful delay between queries
            
        except requests.Timeout:
            logger.warning(f"Reddit timeout for query: {query}")
        except Exception as e:
            logger.error(f"Reddit scrape failed for {tool_name}: {e}")
    
    # Remove duplicates based on text
    seen = set()
    unique_mentions = []
    for m in mentions:
        if m['text'][:100] not in seen:
            seen.add(m['text'][:100])
            unique_mentions.append(m)
    
    logger.info(f"Reddit: found {len(unique_mentions)} mentions for {tool_name}")
    return unique_mentions[:15]  # Cap at 15


# ── Product Hunt ───────────────────────────────────────────────────────────────

def fetch_producthunt_mentions(tool_name: str) -> list:
    """
    Fetch Product Hunt search results and reviews.
    Great source for founder opinions on new tools.
    """
    mentions = []
    url = f"https://www.producthunt.com/search?q={tool_name.replace(' ', '+')}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract paragraphs and description text
        paragraphs = soup.find_all('p')
        for p in paragraphs[:15]:
            text = p.get_text(strip=True)
            if len(text) > 40 and len(text) < 1000:
                mentions.append({
                    "source": "producthunt.com",
                    "text": text[:400]
                })
        
        # Also try to get any review text
        review_divs = soup.find_all('div', class_=lambda x: x and 'review' in x.lower())
        for div in review_divs[:5]:
            text = div.get_text(strip=True)
            if len(text) > 40:
                mentions.append({
                    "source": "producthunt.com",
                    "text": text[:400]
                })
    
    except requests.Timeout:
        logger.warning(f"ProductHunt timeout for {tool_name}")
    except Exception as e:
        logger.error(f"ProductHunt scrape failed for {tool_name}: {e}")
    
    logger.info(f"ProductHunt: found {len(mentions)} mentions for {tool_name}")
    return mentions


# ── Hacker News ────────────────────────────────────────────────────────────────

def fetch_hackernews_mentions(tool_name: str) -> list:
    """
    Fetch Hacker News discussions mentioning a tool.
    Completely free. No API key needed.
    HN has very high quality technical founder opinions.
    """
    mentions = []
    url = (
        f"https://hn.algolia.com/api/v1/search"
        f"?query={tool_name}&tags=comment,story&hitsPerPage=15"
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        for hit in data.get('hits', []):
            text = hit.get('comment_text') or hit.get('title') or ''
            # Strip HTML tags from HN comments
            if '<' in text:
                soup = BeautifulSoup(text, 'html.parser')
                text = soup.get_text(strip=True)
            if len(text.strip()) > 30:
                mentions.append({
                    "source": "news.ycombinator.com",
                    "text": text[:600]
                })

        logger.info(f"HackerNews: found {len(mentions)} mentions for {tool_name}")

    except requests.Timeout:
        logger.warning(f"HackerNews timeout for {tool_name}")
    except Exception as e:
        logger.error(f"HackerNews scrape failed for {tool_name}: {e}")

    return mentions


# ── YouTube ────────────────────────────────────────────────────────────────────

def fetch_youtube_mentions(tool_name: str) -> list:
    """
    Fetch YouTube video titles and descriptions about a tool.
    Especially useful for India-specific content and tutorial reviews.
    Uses YouTube's public search without API key.
    """
    mentions = []
    search_query = f"{tool_name} review tutorial".replace(' ', '+')
    url = f"https://www.youtube.com/results?search_query={search_query}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract any visible text that looks like video descriptions
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and tool_name.lower() in script.string.lower():
                # Extract title-like text snippets
                text = script.string
                start = text.lower().find(tool_name.lower())
                if start != -1:
                    snippet = text[max(0, start-50):start+300]
                    # Clean up the snippet
                    snippet = snippet.replace('\\n', ' ').replace('\\"', '"')
                    if len(snippet) > 50:
                        mentions.append({
                            "source": "youtube.com",
                            "text": snippet[:400]
                        })
                        break

    except requests.Timeout:
        logger.warning(f"YouTube timeout for {tool_name}")
    except Exception as e:
        logger.error(f"YouTube scrape failed for {tool_name}: {e}")

    logger.info(f"YouTube: found {len(mentions)} mentions for {tool_name}")
    return mentions[:5]  # Cap at 5 for YouTube


# ── Trustpilot ─────────────────────────────────────────────────────────────────

def fetch_trustpilot_mentions(tool_name: str) -> list:
    """
    Fetch Trustpilot reviews for a tool.
    Good for consumer-facing AI tools.
    """
    mentions = []
    search_url = f"https://www.trustpilot.com/search?query={tool_name.replace(' ', '+')}"

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract review text
        review_cards = soup.find_all('p', class_=lambda x: x and 'review' in str(x).lower())
        for card in review_cards[:10]:
            text = card.get_text(strip=True)
            if len(text) > 40:
                mentions.append({
                    "source": "trustpilot.com",
                    "text": text[:400]
                })

    except requests.Timeout:
        logger.warning(f"Trustpilot timeout for {tool_name}")
    except Exception as e:
        logger.error(f"Trustpilot scrape failed for {tool_name}: {e}")

    logger.info(f"Trustpilot: found {len(mentions)} mentions for {tool_name}")
    return mentions


# ── Master Gatherer ─────────────────────────────────────────────────────────────

def gather_all_mentions(tool_name: str) -> list:
    """
    Master function that collects mentions from all sources.
    Automation calls this. Agent receives the combined output.
    
    Sources in order of priority:
    1. Reddit (best depth)
    2. Product Hunt (most targeted)
    3. Hacker News (best quality, free)
    4. YouTube (India-specific)
    5. Trustpilot (volume)
    """
    all_mentions = []

    # Source 1. Reddit
    all_mentions.extend(fetch_reddit_mentions(tool_name))
    time.sleep(1)

    # Source 2. Product Hunt
    all_mentions.extend(fetch_producthunt_mentions(tool_name))
    time.sleep(1)

    # Source 3. Hacker News
    all_mentions.extend(fetch_hackernews_mentions(tool_name))
    time.sleep(1)

    # Source 4. YouTube
    all_mentions.extend(fetch_youtube_mentions(tool_name))
    time.sleep(1)

    # Source 5. Trustpilot
    all_mentions.extend(fetch_trustpilot_mentions(tool_name))

    total = len(all_mentions)
    logger.info(f"Total mentions gathered for {tool_name}: {total} across 5 sources")

    return all_mentions