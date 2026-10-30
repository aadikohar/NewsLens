# NewsLens

NewsLens is a news analysis platform that compares how different news outlets report the same event. It collects articles via RSS feeds, performs sentiment and loaded‑wording analysis, clusters related articles, and presents the results in an interactive web dashboard.

## Project Structure

- `fetcher.py` – RSS feed collection and article preprocessing
- `analysis.py` – Sentiment analysis (VADER) and loaded‑wording detection
- `clustering.py` – TF‑IDF vectorization and cosine‑similarity clustering
- `database.py` – SQLite schema and data‑access helpers
- `app.py` – Flask REST API and web server
- `static/` – Front‑end assets (HTML, CSS, JavaScript)
- `requirements.txt` – Python dependencies

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Run the server with:

```bash
python app.py
```

The dashboard will be available at `http://localhost:5000`.
