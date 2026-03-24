import requests
from bs4 import BeautifulSoup
import time
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; One9FoundersBot/1.0)"
}

def fetch_reddit_mentions(tool_name: str) -> list:
    mentions = []
    url = f"https://www.reddit.com/search.json?q={tool_name}+review&sort=new&limit=15"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        for post in data['data']['children']:
            d = post['data']
            title = d.get('title', '')
            body = d.get('selftext', '')
            subreddit = d.get('subreddit', '')
            combined = f"{title} {body}".strip()
            if len(combined) > 30:
                mentions.append({
                    "source": f"reddit.com/r/{subreddit}",
                    "text": combined[:600]
                })
        logger.info(f"Reddit: found {len(mentions)} mentions for {tool_name}")
    except requests.Timeout:
        logger.warning(f"Reddit timeout for {tool_name}")
    except Exception as e:
        logger.error(f"Reddit scrape failed for {tool_name}: {e}")
    return mentions


def fetch_producthunt_mentions(tool_name: str) -> list:
    mentions = []
    url = f"https://www.producthunt.com/search?q={tool_name.replace(' ', '+')}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        for p in paragraphs[:10]:
            text = p.get_text(strip=True)
            if len(text) > 40:
                mentions.append({
                    "source": "producthunt.com",
                    "text": text[:400]
                })
    except Exception as e:
        logger.error(f"ProductHunt scrape failed for {tool_name}: {e}")
    return mentions


def gather_all_mentions(tool_name: str) -> list:
    all_mentions = []
    all_mentions.extend(fetch_reddit_mentions(tool_name))
    time.sleep(1)
    all_mentions.extend(fetch_producthunt_mentions(tool_name))
    logger.info(f"Total mentions gathered for {tool_name}: {len(all_mentions)}")
    return all_mentions