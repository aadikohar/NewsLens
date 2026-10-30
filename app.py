# pyrefly: ignore[missing-import]
from flask import Flask, jsonify, abort, request
import json
import logging
from pathlib import Path

# Local imports from project modules (they live in the workspace root)
import sys
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR.parent))

from database import (
    get_connection,
    get_all_topics,
    init_db,
    add_topic,
    delete_topic,
    assign_articles_to_topic,
    get_available_articles,
    find_articles_by_keywords,
)
from clustering import cluster_articles

app = Flask(__name__, static_folder=str(Path(__file__).parent / 'static'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def row_to_dict(row):
    return dict(row)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/api/sources', methods=['GET'])
def get_sources():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT source_id, name, feed_url, enabled, last_success, last_error FROM sources')
    sources = [row_to_dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(sources)

@app.route('/api/topics', methods=['GET'])
def list_topics():
    topics = get_all_topics()
    return jsonify(topics)

@app.route('/api/topics', methods=['POST'])
def create_new_topic():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({"error": "Topic title is required"}), 400

    topic_id = add_topic(title)

    # Check for direct article IDs
    article_ids = set()
    raw_ids = data.get('article_ids')
    if isinstance(raw_ids, list):
        for aid in raw_ids:
            try:
                article_ids.add(int(aid))
            except (ValueError, TypeError):
                pass

    # Check for keyword matching
    keywords = data.get('keywords')
    if keywords:
        if isinstance(keywords, str):
            kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
        elif isinstance(keywords, list):
            kw_list = [str(k).strip() for k in keywords if str(k).strip()]
        else:
            kw_list = []
        if kw_list:
            matched = find_articles_by_keywords(kw_list)
            article_ids.update(matched)

    assigned_count = 0
    if article_ids:
        assigned_count = assign_articles_to_topic(topic_id, list(article_ids))

    return jsonify({
        "status": "ok",
        "topic": {
            "topic_id": topic_id,
            "title": title,
            "article_count": assigned_count
        }
    }), 201

@app.route('/api/topics/<int:topic_id>', methods=['DELETE'])
def remove_topic(topic_id):
    success = delete_topic(topic_id)
    if not success:
        abort(404, description="Topic not found")
    return jsonify({"status": "ok", "message": f"Topic #{topic_id} deleted"})

@app.route('/api/topics/cluster', methods=['POST'])
def run_cluster():
    data = request.get_json(silent=True) or {}
    threshold = float(data.get('similarity_threshold', 0.22))
    stats = cluster_articles(similarity_threshold=threshold)
    return jsonify({
        "status": "ok",
        "new_topics": stats.get("new_topics", 0),
        "clustered_articles": stats.get("clustered_articles", 0)
    })

@app.route('/api/articles', methods=['GET'])
def list_articles():
    search = request.args.get('search', '').strip()
    limit = min(int(request.args.get('limit', 50)), 200)
    unassigned_only = request.args.get('unassigned_only', '0') in ('1', 'true', 'True')
    articles = get_available_articles(search=search, limit=limit, unassigned_only=unassigned_only)
    return jsonify({"articles": articles})

@app.route('/api/articles/match-keywords', methods=['GET'])
def preview_keyword_match():
    raw_kw = request.args.get('keywords', '').strip()
    if not raw_kw:
        return jsonify({"count": 0, "article_ids": []})
    keywords = [k.strip() for k in raw_kw.split(',') if k.strip()]
    matched_ids = find_articles_by_keywords(keywords)
    return jsonify({"count": len(matched_ids), "article_ids": matched_ids})

@app.route('/api/topics/<int:topic_id>/compare', methods=['GET'])
def compare_topic(topic_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.article_id, a.headline, a.url, a.publication_date, a.clean_text,
               s.name AS source_name,
               an.headline_sentiment, an.body_sentiment, an.loaded_wording_pct,
               an.flagged_sentences
        FROM articles a
        JOIN sources s ON a.source_id = s.source_id
        LEFT JOIN analysis an ON a.article_id = an.article_id
        WHERE a.topic_id = ?
        """,
        (topic_id,)
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        abort(404, description="Topic not found or has no articles")
    articles = []
    for r in rows:
        article = row_to_dict(r)
        flagged = article.get('flagged_sentences')
        if flagged:
            try:
                article['flagged_sentences'] = json.loads(flagged)
            except Exception:
                article['flagged_sentences'] = []
        else:
            article['flagged_sentences'] = []
        articles.append(article)
    return jsonify({"topic_id": topic_id, "articles": articles})

@app.route('/api/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.article_id, a.headline, a.url, a.publication_date, a.clean_text,
               s.name AS source_name,
               an.headline_sentiment, an.body_sentiment, an.loaded_wording_pct,
               an.flagged_sentences, an.version, an.analyzed_at
        FROM articles a
        JOIN sources s ON a.source_id = s.source_id
        LEFT JOIN analysis an ON a.article_id = an.article_id
        WHERE a.article_id = ?
        """,
        (article_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404, description="Article not found")
    article = row_to_dict(row)
    flagged = article.get('flagged_sentences')
    if flagged:
        try:
            article['flagged_sentences'] = json.loads(flagged)
        except Exception:
            article['flagged_sentences'] = []
    else:
        article['flagged_sentences'] = []
    return jsonify(article)

# Serve the front‑end index page
@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    init_db()
    app.static_folder = str(Path(__file__).parent / 'static')
    app.run(host='0.0.0.0', port=5000, debug=True)
