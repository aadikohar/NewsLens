"""pipeline.py – Full NewsLens data pipeline runner.

Steps:
  1. Wipe existing sources / articles / analysis / topics (fresh start)
  2. Seed Indian news sources
  3. Fetch all RSS feeds
  4. Analyse all articles
  5. Cluster articles into topics
"""

import logging
import sqlite3
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH  = BASE_DIR / "newslens.db"


def wipe_db() -> None:
    """Delete all rows so we start fresh with Indian sources."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    # Order matters: child tables first
    cur.executescript("""
        DELETE FROM analysis;
        DELETE FROM articles;
        DELETE FROM topics;
        DELETE FROM sources;
    """)
    conn.commit()
    conn.close()
    logging.info("Database wiped – ready for fresh data.")


if __name__ == "__main__":
    # ── Step 1: fresh start ────────────────────────────────────────
    from database import init_db
    init_db()
    wipe_db()

    # ── Step 2 & 3: seed sources + fetch articles ──────────────────
    from fetcher import seed_indian_sources, fetch_all_feeds
    logging.info("=== Seeding Indian sources ===")
    seed_indian_sources()
    logging.info("=== Fetching RSS feeds ===")
    fetch_all_feeds()

    # ── Step 4: analyse pending articles ──────────────────────────
    logging.info("=== Running sentiment / loaded-wording analysis ===")
    from analysis import analyse_pending_articles
    analyse_pending_articles()

    # ── Step 5: cluster into topics ───────────────────────────────
    logging.info("=== Clustering articles into topics ===")
    from clustering import cluster_articles
    cluster_articles(similarity_threshold=0.25)

    logging.info("=== Pipeline complete – open http://localhost:5000 ===")
