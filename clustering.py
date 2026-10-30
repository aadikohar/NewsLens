import logging
import re
from typing import List, Tuple, Dict, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database import get_connection

# Simple configuration
DEFAULT_SIMILARITY_THRESHOLD = 0.22

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def clean_title(title: str) -> str:
    """Clean headline text for use as a readable topic title."""
    if not title:
        return "Topic"
    # Clean up common encoding artifacts
    title = title.replace("\ufffd", "'")
    # Remove trailing outlet suffixes
    title = re.sub(
        r"\s*(\||–|-)\s*(News18|NDTV|The Hindu|The Indian Express|Times of India|Hindustan Times|India Today|Mint|Scroll|Wire|Outlook|Zee News|Firstpost|Deccan Herald|BBC|CNN).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = title.strip().strip("-|:;, ")
    return title or "Topic"


def fetch_unclustered_articles() -> List[Dict]:
    """Return a list of article rows without a topic assignment."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT article_id, headline, clean_text FROM articles WHERE topic_id IS NULL")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def create_topic(title: str) -> int:
    """Insert a new topic and return its ID."""
    conn = get_connection()
    cur = conn.cursor()
    clean_t = clean_title(title)
    cur.execute(
        "INSERT INTO topics (title, created_at, article_count) VALUES (?, datetime('now'), 0)",
        (clean_t,),
    )
    topic_id = cur.lastrowid
    conn.commit()
    conn.close()
    return topic_id


def assign_articles_to_topic(article_ids: List[int], topic_id: int) -> int:
    """Assign a list of articles to a topic and update the topic's article_count."""
    if not article_ids:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?" for _ in article_ids])
    cur.execute(
        f"UPDATE articles SET topic_id = ? WHERE article_id IN ({placeholders})",
        (topic_id, *article_ids),
    )
    assigned_count = cur.rowcount

    # Sync the exact article count
    cur.execute(
        "UPDATE topics SET article_count = (SELECT COUNT(*) FROM articles WHERE topic_id = ?) WHERE topic_id = ?",
        (topic_id, topic_id),
    )
    conn.commit()
    conn.close()
    return assigned_count


def cluster_articles(similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> Dict[str, int]:
    """Cluster unassigned articles into topics using weighted TF-IDF and cosine similarity.

    Returns dict with stats: {'new_topics': count, 'clustered_articles': count}.
    """
    articles = fetch_unclustered_articles()
    if not articles:
        logging.info("No unclustered articles found.")
        return {"new_topics": 0, "clustered_articles": 0}

    # Weight the headline twice + first 600 chars of body text for higher topic alignment
    texts = [f"{a['headline']} {a['headline']} {a['clean_text'][:600]}" for a in articles]
    ids = [a["article_id"] for a in articles]

    vectorizer = TfidfVectorizer(stop_words="english", max_df=0.85, min_df=2)
    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError as e:
        logging.warning(f"TF-IDF vectorizer could not fit (likely too few unique terms): {e}")
        return {"new_topics": 0, "clustered_articles": 0}

    similarity = cosine_similarity(tfidf_matrix)

    clustered = set()
    new_topics_count = 0
    total_clustered_articles = 0

    for i, article_id in enumerate(ids):
        if article_id in clustered:
            continue
        # Find indices with similarity above threshold (only among unclustered)
        peers_idx = [
            j for j, sim in enumerate(similarity[i])
            if sim >= similarity_threshold and ids[j] not in clustered
        ]
        peer_ids = [ids[j] for j in peers_idx]

        # Require at least 2 articles to form a comparison topic
        if len(peer_ids) < 2:
            continue

        raw_title = articles[i].get("headline") or "News Topic"
        topic_id = create_topic(raw_title)
        assigned = assign_articles_to_topic(peer_ids, topic_id)
        clustered.update(peer_ids)

        new_topics_count += 1
        total_clustered_articles += assigned
        logging.info(f"Created topic {topic_id} ('{clean_title(raw_title)[:50]}...') with {assigned} articles.")

    logging.info(
        f"Clustering complete. Created {new_topics_count} new topics with {total_clustered_articles} articles."
    )
    return {"new_topics": new_topics_count, "clustered_articles": total_clustered_articles}


def recluster_all(similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> Dict[str, int]:
    """Reset all topics and re-cluster the entire article catalog cleanly."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE articles SET topic_id = NULL")
    cur.execute("DELETE FROM topics")
    conn.commit()
    conn.close()
    return cluster_articles(similarity_threshold=similarity_threshold)


if __name__ == "__main__":
    cluster_articles()
    logging.info("Clustering run complete.")
