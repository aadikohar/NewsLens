import json
import logging
from typing import List, Tuple

from nltk import sent_tokenize
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from nltk import download as nltk_download
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Local import from our database helpers
from database import add_analysis, get_connection

import os
import re

# Ensure required NLTK data is available (run once)
try:
    _ = sent_tokenize("test")
except Exception:
    try:
        if os.environ.get("VERCEL"):
            tmp_nltk = "/tmp/nltk_data"
            os.makedirs(tmp_nltk, exist_ok=True)
            import nltk
            nltk.data.path.append(tmp_nltk)
            nltk_download("punkt", download_dir=tmp_nltk, quiet=True)
        else:
            nltk_download("punkt", quiet=True)
    except Exception:
        pass


def safe_sent_tokenize(text: str) -> List[str]:
    """Tokenize sentences using NLTK with regex fallback."""
    try:
        return sent_tokenize(text)
    except Exception:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        return sentences or [text]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Loaded‑wording lexicon (configurable – can be extended or loaded from a file)
# ---------------------------------------------------------------------------
DEFAULT_LOADED_WORDS = {
    "allegedly",
    "claims",
    "rumour",
    "speculation",
    "dangerous",
    "shocking",
    "outrage",
    "biased",
    "unfair",
    "blatant",
    "exaggerated",
    "disaster",
    "catastrophe",
    "scandal",
    "controversial",
    "provocative",
    "dramatic",
    "savage",
    "harsh",
    "outrageous",
    "unacceptable",
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_quoted(sentence: str) -> bool:
    """Return True if the sentence appears to be a quoted speech.

    Simple heuristic: sentence starts and ends with a double‑quote or single‑quote.
    """
    stripped = sentence.strip()
    return (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    )


def flag_loaded_wording(sentences: List[str], lexicon: set = DEFAULT_LOADED_WORDS) -> List[str]:
    """Return sentences that contain any word from the loaded‑wording lexicon.
    Matching is case‑insensitive and works on word boundaries.
    """
    flagged: List[str] = []
    for s in sentences:
        lower = s.lower()
        for word in lexicon:
            if f" {word} " in f" {lower} " or lower.startswith(f"{word} ") or lower.endswith(f" {word}"):
                flagged.append(s)
                break
    return flagged


def compute_loaded_wording_percentage(eligible_sentences: List[str], flagged_sentences: List[str]) -> float:
    if not eligible_sentences:
        return 0.0
    return round(100.0 * len(flagged_sentences) / len(eligible_sentences), 2)

# ---------------------------------------------------------------------------
# Core analysis routine
# ---------------------------------------------------------------------------

def analyze_article(
    article_id: int,
    headline: str,
    body_text: str,
    version: str = "1.0",
) -> Tuple[float, float, float, List[str]]:
    """Perform sentiment and loaded‑wording analysis on a single article.

    Returns:
        headline_sentiment (float) – VADER compound score for the headline
        body_sentiment (float) – VADER compound score for the full body
        loaded_wording_pct (float) – percentage of eligible sentences flagged
        flagged_sentences (list) – the exact sentences that triggered the flag
    """
    analyzer = SentimentIntensityAnalyzer()

    # Headline sentiment
    headline_score = analyzer.polarity_scores(headline).get("compound", 0.0)

    # Split body into sentences
    sentences = safe_sent_tokenize(body_text)
    # Exclude quoted speech for loaded‑wording calculations
    eligible_sentences = [s for s in sentences if not is_quoted(s)]
    flagged = flag_loaded_wording(eligible_sentences)
    loaded_pct = compute_loaded_wording_percentage(eligible_sentences, flagged)

    # Body sentiment – we can compute on the whole text for simplicity
    body_score = analyzer.polarity_scores(body_text).get("compound", 0.0)

    # Persist the results
    add_analysis(
        article_id=article_id,
        headline_sentiment=headline_score,
        body_sentiment=body_score,
        loaded_wording_pct=loaded_pct,
        flagged_sentences=flagged,
        version=version,
    )

    logging.info(
        f"Analyzed article {article_id}: headline_sent={headline_score:.3f}, "
        f"body_sent={body_score:.3f}, loaded%={loaded_pct:.1f} ({len(flagged)} flagged)"
    )
    return headline_score, body_score, loaded_pct, flagged

# ---------------------------------------------------------------------------
# Convenience wrapper to analyse all unanalyzed articles
# ---------------------------------------------------------------------------

def analyse_pending_articles() -> None:
    """Find articles without a corresponding entry in ``analysis`` and process them.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.article_id, a.headline, a.clean_text
        FROM articles a
        LEFT JOIN analysis an ON a.article_id = an.article_id
        WHERE an.article_id IS NULL
        """
    )
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        article_id = row["article_id"]
        headline = row["headline"]
        text = row["clean_text"]
        analyze_article(article_id, headline, text)

if __name__ == "__main__":
    analyse_pending_articles()
    logging.info("All pending articles have been analysed.")
