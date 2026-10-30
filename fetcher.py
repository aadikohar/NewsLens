import feedparser
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Optional

# Local imports from the generated database module
from database import (
    get_connection,
    add_source,
    add_article,
    init_db,
)

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def clean_html(html: str) -> str:
    """Return plain text extracted from HTML.

    Very simple extraction: strip tags and concatenate the text of <p> elements.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Prefer paragraph text; fallback to all visible text
    paragraphs = soup.find_all("p")
    if paragraphs:
        text = "\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    else:
        text = soup.get_text(separator=" ", strip=True)
    # Collapse multiple whitespace
    return " ".join(text.split())


def fetch_article_text(url: str, timeout: int = 10) -> Optional[str]:
    """Download the article page and return cleaned text.
    Returns ``None`` on network errors or if the page cannot be parsed.
    """
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "NewsLensFetcher/1.0"})
        resp.raise_for_status()
        return clean_html(resp.text)
    except Exception as e:
        logging.warning(f"Failed to fetch article {url}: {e}")
        return None

# ---------------------------------------------------------------------------
# Core fetcher logic
# ---------------------------------------------------------------------------

def fetch_and_store_feed(source_id: int, feed_url: str) -> None:
    """Parse a single RSS/Atom feed and store new articles.

    * Duplicate URLs are ignored thanks to the UNIQUE constraint in the
      ``articles`` table.
    * Articles with very short bodies (<200 characters) are skipped – they
      provide little value for sentiment/loaded‑wording analysis.
    """
    logging.info(f"Fetching feed from {feed_url}")
    feed = feedparser.parse(feed_url)
    if feed.bozo:
        logging.error(f"Error parsing feed {feed_url}: {feed.bozo_exception}")
        return

    for entry in feed.entries:
        # Basic metadata – RSS/Atom formats differ, so we fall back gracefully.
        url = entry.get("link") or entry.get("id")
        if not url:
            continue
        title = entry.get("title", "")
        published = entry.get("published") or entry.get("updated") or None
        # Some feeds already include a cleaned summary; otherwise we fetch the article.
        summary_html = entry.get("summary") or entry.get("description") or ""
        article_text = clean_html(summary_html) if summary_html else None

        if not article_text:
            article_text = fetch_article_text(url)
        if not article_text:
            # If we still have no text, skip this entry.
            logging.info(f"Skipping entry without extractable text: {url}")
            continue
        # Minimum length filter (configurable – here 80 chars)
        if len(article_text) < 80:
            logging.info(f"Skipping short article ({len(article_text)} chars): {url}")
            continue

        # Insert article; duplicates are ignored automatically.
        article_id = add_article(
            source_id=source_id,
            headline=title,
            url=url,
            publication_date=published,
            clean_text=article_text,
        )
        if article_id:
            logging.info(f"Stored article {article_id} from {url}")
        else:
            logging.debug(f"Article already exists (duplicate URL): {url}")


def fetch_all_feeds(min_interval_seconds: int = 0) -> None:
    """Iterate over enabled sources and fetch their feeds.

    ``min_interval_seconds`` can be used to throttle requests when running
    repeatedly (e.g., from a scheduler). For a one‑off run keep it ``0``.
    """
    init_db()  # Ensure tables exist before we query them.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT source_id, feed_url FROM sources WHERE enabled = 1")
    sources = cur.fetchall()
    conn.close()
    for row in sources:
        source_id = row["source_id"]
        feed_url = row["feed_url"]
        fetch_and_store_feed(source_id, feed_url)
        if min_interval_seconds:
            import time
            time.sleep(min_interval_seconds)

# ---------------------------------------------------------------------------
# Example usage (run as script)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Indian news source catalogue
# ---------------------------------------------------------------------------
INDIAN_SOURCES = [
    ("NDTV – Top Stories",       "https://feeds.feedburner.com/ndtvnews-top-stories"),
    ("NDTV – India",             "https://feeds.feedburner.com/ndtvnews-india-news"),
    ("The Hindu – National",     "https://www.thehindu.com/news/national/?service=rss"),
    ("The Hindu – Business",     "https://www.thehindu.com/business/?service=rss"),
    ("Times of India – India",   "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms"),
    ("Times of India – Business","https://timesofindia.indiatimes.com/rssfeeds/1898055.cms"),
    ("Hindustan Times – India",  "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"),
    ("Indian Express – India",   "https://indianexpress.com/section/india/feed/"),
    ("India Today – India",      "https://www.indiatoday.in/rss/1206578"),
    ("The Wire – India",         "https://thewire.in/category/india/feed"),
    ("News18 – India",           "https://www.news18.com/rss/india.xml"),
    ("Zee News – India",         "https://zeenews.india.com/rss/india-national-news.xml"),
]


def seed_indian_sources() -> None:
    """Ensure all Indian news sources are registered in the database.

    Safe to call repeatedly – uses INSERT OR IGNORE so existing sources
    are not duplicated.
    """
    init_db()
    for name, url in INDIAN_SOURCES:
        added = add_source(name, url)
        if added:
            logging.info(f"Registered source: {name}")
        else:
            logging.debug(f"Source already exists (skipped): {name}")


if __name__ == "__main__":
    seed_indian_sources()
    fetch_all_feeds()
    logging.info("Fetching complete.")

