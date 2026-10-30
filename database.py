import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import os
import shutil

# Base directory for the project (relative to this file's location)
BASE_DIR = Path(__file__).resolve().parent

# On Vercel serverless functions, the deployment directory is read-only.
# We copy newslens.db to /tmp so SQLite can open, read and write freely.
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp") / "newslens.db"
    source_db = BASE_DIR / "newslens.db"
    if not DB_PATH.exists() and source_db.exists():
        try:
            shutil.copy2(source_db, DB_PATH)
        except Exception:
            DB_PATH = source_db
else:
    DB_PATH = BASE_DIR / "newslens.db"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with dict‑like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the required tables if they do not already exist.

    Tables:
    * sources – metadata about RSS feeds
    * topics  – clustering results
    * articles – raw article data
    * analysis – sentiment and loaded‑wording results
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources (
            source_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            feed_url       TEXT NOT NULL UNIQUE,
            enabled        INTEGER NOT NULL DEFAULT 1,
            last_success   TEXT,
            last_error     TEXT
        );

        CREATE TABLE IF NOT EXISTS topics (
            topic_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT,
            created_at     TEXT NOT NULL,
            article_count  INTEGER NOT NULL DEFAULT 0,
            clustering_cfg TEXT
        );

        CREATE TABLE IF NOT EXISTS articles (
            article_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id        INTEGER NOT NULL,
            headline         TEXT NOT NULL,
            url              TEXT NOT NULL UNIQUE,
            publication_date TEXT,
            clean_text       TEXT NOT NULL,
            topic_id         INTEGER,
            collected_at     TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES sources(source_id),
            FOREIGN KEY(topic_id)  REFERENCES topics(topic_id)
        );

        CREATE TABLE IF NOT EXISTS analysis (
            analysis_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id           INTEGER NOT NULL UNIQUE,
            headline_sentiment   REAL NOT NULL,
            body_sentiment       REAL NOT NULL,
            loaded_wording_pct   REAL NOT NULL,
            flagged_sentences    TEXT, -- JSON‑encoded list
            version              TEXT NOT NULL,
            analyzed_at          TEXT NOT NULL,
            FOREIGN KEY(article_id) REFERENCES articles(article_id)
        );
        """
    )
    conn.commit()
    conn.close()

# -------------------------------------------------------------------
# Helper functions for common operations
# -------------------------------------------------------------------

def add_source(name: str, feed_url: str, enabled: bool = True) -> int:
    """Insert a new source or ignore if the feed URL already exists.
    Returns the generated source_id (0 if ignored)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO sources (name, feed_url, enabled) VALUES (?, ?, ?)",
        (name, feed_url, int(enabled)),
    )
    conn.commit()
    source_id = cur.lastrowid
    conn.close()
    return source_id


def add_article(
    source_id: int,
    headline: str,
    url: str,
    publication_date: Optional[str],
    clean_text: str,
    topic_id: Optional[int] = None,
) -> int:
    """Insert a new article; duplicates (same URL) are ignored.
    Returns the article_id (0 if ignored)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO articles (
            source_id, headline, url, publication_date, clean_text, topic_id, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (source_id, headline, url, publication_date, clean_text, topic_id),
    )
    conn.commit()
    article_id = cur.lastrowid
    conn.close()
    return article_id


def add_topic(title: str) -> int:
    """Insert a new topic and return its ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO topics (title, created_at, article_count) VALUES (?, datetime('now'), 0)",
        (title,)
    )
    topic_id = cur.lastrowid
    conn.commit()
    conn.close()
    return topic_id


def add_analysis(
    article_id: int,
    headline_sentiment: float,
    body_sentiment: float,
    loaded_wording_pct: float,
    flagged_sentences: List[str],
    version: str = "1.0",
) -> int:
    """Insert or replace analysis results for an article.
    Returns the analysis_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO analysis (
            article_id, headline_sentiment, body_sentiment, loaded_wording_pct,
            flagged_sentences, version, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            article_id,
            headline_sentiment,
            body_sentiment,
            loaded_wording_pct,
            json.dumps(flagged_sentences),
            version,
        ),
    )
    conn.commit()
    analysis_id = cur.lastrowid
    conn.close()
    return analysis_id


def get_all_topics() -> List[Dict[str, Any]]:
    """Return a list of all topics as dictionaries."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM topics")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_topic(topic_id: int) -> bool:
    """Delete a topic and unlink its articles."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE articles SET topic_id = NULL WHERE topic_id = ?", (topic_id,))
    cur.execute("DELETE FROM topics WHERE topic_id = ?", (topic_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def assign_articles_to_topic(topic_id: int, article_ids: List[int]) -> int:
    """Assign articles to a topic and update topic article count."""
    if not article_ids:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?" for _ in article_ids])
    cur.execute(
        f"UPDATE articles SET topic_id = ? WHERE article_id IN ({placeholders})",
        (topic_id, *article_ids),
    )
    count = cur.rowcount
    cur.execute(
        "UPDATE topics SET article_count = (SELECT COUNT(*) FROM articles WHERE topic_id = ?) WHERE topic_id = ?",
        (topic_id, topic_id),
    )
    conn.commit()
    conn.close()
    return count


def get_available_articles(search: str = "", limit: int = 50, unassigned_only: bool = False) -> List[Dict[str, Any]]:
    """Fetch articles for topic assignment."""
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT a.article_id, a.headline, a.publication_date, a.topic_id, s.name AS source_name
        FROM articles a
        JOIN sources s ON a.source_id = s.source_id
        WHERE 1=1
    """
    params = []
    if unassigned_only:
        query += " AND a.topic_id IS NULL"
    if search:
        query += " AND (a.headline LIKE ? OR a.clean_text LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])
    query += " ORDER BY a.publication_date DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_articles_by_keywords(keywords: List[str], unassigned_only: bool = False) -> List[int]:
    """Find article IDs matching any of the given keywords."""
    if not keywords:
        return []
    conn = get_connection()
    cur = conn.cursor()
    conditions = []
    params = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        term = f"%{kw}%"
        conditions.append("(a.headline LIKE ? OR a.clean_text LIKE ?)")
        params.extend([term, term])

    if not conditions:
        conn.close()
        return []

    where_clause = " OR ".join(conditions)
    query = f"SELECT a.article_id FROM articles a WHERE ({where_clause})"
    if unassigned_only:
        query += " AND a.topic_id IS NULL"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return [r["article_id"] for r in rows]

# Initialise the database when this module is executed directly
if __name__ == "__main__":
    init_db()
    print(f"Database initialised at {DB_PATH}")
