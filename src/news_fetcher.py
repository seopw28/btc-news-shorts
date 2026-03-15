"""
Bitcoin news fetcher - collects headlines from multiple sources.

Improvements:
- Retry logic with exponential backoff
- Price validation (abort on failure instead of returning 0)
- HTML tag cleaning from RSS summaries
- News deduplication (title similarity)
- Article history tracking (avoid repeating same stories)
- Market sentiment detection (surge/crash/sideways)
"""

import json
import re
import time
import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher


# RSS feeds for Bitcoin/crypto news
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]

# History file to track previously used articles (top-level data/ for easy access)
HISTORY_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = HISTORY_DIR / "article_history.json"

# Similarity threshold for deduplication (0.0 ~ 1.0)
DEDUP_THRESHOLD = 0.6


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode common entities from RSS summary text."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&apos;": "'",
        "&nbsp;": " ", "&#8217;": "'", "&#8220;": '"', "&#8221;": '"',
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two article titles."""
    a_clean = re.sub(r"[^a-z0-9 ]", "", a.lower())
    b_clean = re.sub(r"[^a-z0-9 ]", "", b.lower())
    return SequenceMatcher(None, a_clean, b_clean).ratio()


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove articles with similar titles, keeping the first occurrence."""
    unique = []
    for article in articles:
        is_dup = False
        for kept in unique:
            if _title_similarity(article["title"], kept["title"]) > DEDUP_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            unique.append(article)
    return unique


def _load_history() -> dict:
    """Load article history from JSON file."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"used_articles": [], "last_updated": None}


def _save_history(history: dict):
    """Save article history to JSON file."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history["last_updated"] = datetime.now().isoformat()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _filter_already_used(articles: list[dict], history: dict) -> list[dict]:
    """Filter out articles that were already used in previous runs."""
    used_titles = [a["title"] for a in history.get("used_articles", [])]
    filtered = []
    for article in articles:
        is_used = False
        for used_title in used_titles:
            if _title_similarity(article["title"], used_title) > DEDUP_THRESHOLD:
                is_used = True
                break
        if not is_used:
            filtered.append(article)
    return filtered


def mark_articles_used(articles: list[dict]):
    """Mark articles as used so they won't be selected again."""
    history = _load_history()
    for article in articles:
        history["used_articles"].append({
            "title": article["title"],
            "source": article.get("source", ""),
            "used_at": datetime.now().isoformat(),
        })
    # Keep only last 200 entries to prevent file bloat
    history["used_articles"] = history["used_articles"][-200:]
    _save_history(history)


def _retry_request(fn, max_retries: int = 3, base_delay: float = 2.0):
    """Execute a function with exponential backoff retry."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  [RETRY] Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay:.0f}s...")
                time.sleep(delay)
    raise last_error


def fetch_rss_news(max_age_hours: int = 24) -> list[dict]:
    """Fetch recent Bitcoin news from RSS feeds with deduplication and history filtering."""
    articles = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    success_count = 0

    for feed_url in RSS_FEEDS:
        try:
            def _fetch(url=feed_url):
                return feedparser.parse(url)

            feed = _retry_request(_fetch, max_retries=2, base_delay=3.0)
            success_count += 1

            for entry in feed.entries[:10]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                if published and published < cutoff:
                    continue

                articles.append({
                    "title": _clean_html(entry.get("title", "")),
                    "summary": _clean_html(entry.get("summary", ""))[:300],
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", feed_url),
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            print(f"[WARN] Failed to fetch {feed_url}: {e}")

    if success_count == 0:
        print("[ERROR] All RSS feeds failed!")

    # Sort by published date (newest first), None dates last
    articles.sort(key=lambda a: a["published"] or "", reverse=True)

    # Deduplicate similar titles
    before_dedup = len(articles)
    articles = _deduplicate_articles(articles)
    if before_dedup != len(articles):
        print(f"  [DEDUP] Removed {before_dedup - len(articles)} duplicate articles")

    # Filter out previously used articles
    history = _load_history()
    before_filter = len(articles)
    articles = _filter_already_used(articles, history)
    if before_filter != len(articles):
        print(f"  [HISTORY] Filtered {before_filter - len(articles)} previously used articles")

    return articles


def fetch_bitcoin_price() -> dict | None:
    """Fetch current Bitcoin price, 24h change, high/low/volume from CoinGecko.
    Returns None if all attempts fail (pipeline should handle this).
    """
    url = "https://api.coingecko.com/api/v3/coins/bitcoin"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }

    def _fetch():
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        market = resp.json().get("market_data", {})
        price_usd = market.get("current_price", {}).get("usd", 0)
        if price_usd <= 0:
            raise ValueError(f"Invalid BTC price: {price_usd}")
        return {
            "price_usd": price_usd,
            "change_24h": round(market.get("price_change_percentage_24h", 0), 2),
            "market_cap": market.get("market_cap", {}).get("usd", 0),
            "high_24h": market.get("high_24h", {}).get("usd", 0),
            "low_24h": market.get("low_24h", {}).get("usd", 0),
            "volume_24h": market.get("total_volume", {}).get("usd", 0),
        }

    try:
        return _retry_request(_fetch, max_retries=3, base_delay=3.0)
    except Exception as e:
        print(f"[ERROR] Failed to fetch BTC price after retries: {e}")
        return None


def fetch_fear_greed() -> dict | None:
    """Fetch Bitcoin Fear & Greed Index from alternative.me."""
    url = "https://api.alternative.me/fng/"

    def _fetch():
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [{}])[0]
        return {
            "value": int(data.get("value", 50)),
            "label": data.get("value_classification", "Neutral"),
        }

    try:
        return _retry_request(_fetch, max_retries=2, base_delay=2.0)
    except Exception as e:
        print(f"[WARN] Fear & Greed fetch failed: {e}")
        return None


def detect_market_sentiment(price_data: dict) -> str:
    """Detect market sentiment based on 24h price change.
    Returns: 'surge', 'crash', 'bullish', 'bearish', or 'sideways'.
    Used to adjust script tone and energy level.
    """
    if not price_data:
        return "sideways"

    change = price_data.get("change_24h", 0)

    if change >= 5.0:
        return "surge"      # 급등 (5%+)
    elif change >= 2.0:
        return "bullish"    # 상승세 (2~5%)
    elif change <= -5.0:
        return "crash"      # 급락 (-5%+)
    elif change <= -2.0:
        return "bearish"    # 하락세 (-2~-5%)
    else:
        return "sideways"   # 횡보 (-2~+2%)


def fetch_all() -> dict:
    """Fetch all news data and price info.
    Returns dict with 'articles', 'price', 'sentiment', 'fear_greed', 'fetched_at'.
    price can be None if API fails - pipeline must handle this.
    """
    price = fetch_bitcoin_price()
    articles = fetch_rss_news()
    sentiment = detect_market_sentiment(price)
    fear_greed = fetch_fear_greed()

    if sentiment in ("surge", "crash"):
        print(f"  [MARKET] Detected {sentiment.upper()} ({price['change_24h']:+.2f}%)")
    if fear_greed:
        print(f"  [F&G] Fear & Greed: {fear_greed['value']} ({fear_greed['label']})")

    return {
        "articles": articles,
        "price": price,
        "sentiment": sentiment,
        "fear_greed": fear_greed,
        "fetched_at": datetime.now().isoformat(),
    }


def show_history(limit: int = 30):
    """Display article usage history."""
    history = _load_history()
    articles = history.get("used_articles", [])

    if not articles:
        print("[HISTORY] No articles used yet.")
        return

    print(f"\n{'='*60}")
    print(f"  Article History ({len(articles)} total, showing last {min(limit, len(articles))})")
    print(f"  Last updated: {history.get('last_updated', 'N/A')}")
    print(f"{'='*60}\n")

    for i, article in enumerate(reversed(articles[-limit:]), 1):
        used_at = article.get("used_at", "?")[:10]  # date only
        source = article.get("source", "?")[:15].ljust(15)
        title = article["title"][:60]
        print(f"  {i:3d}. [{used_at}] {source} {title}")

    print()


def show_available(max_age_hours: int = 24):
    """Fetch and display currently available (unused) articles."""
    print("\n[FETCH] Fetching current articles...")
    articles = fetch_rss_news(max_age_hours=max_age_hours)

    if not articles:
        print("[INFO] No new articles available.")
        return

    print(f"\n{'='*60}")
    print(f"  Available Articles ({len(articles)} new, deduplicated)")
    print(f"{'='*60}\n")

    for i, article in enumerate(articles[:15], 1):
        source = article.get("source", "?")[:15].ljust(15)
        published = (article.get("published") or "?")[:16]
        title = article["title"][:55]
        print(f"  {i:3d}. [{published}] {source} {title}")
        if article.get("summary"):
            print(f"       {article['summary'][:70]}...")

    print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "history":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            show_history(limit)
        elif cmd == "available":
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            show_available(max_age_hours=hours)
        elif cmd == "clear-history":
            _save_history({"used_articles": []})
            print("[OK] Article history cleared.")
        else:
            print("Usage:")
            print("  python -m src.news_fetcher              # Fetch all (default)")
            print("  python -m src.news_fetcher available     # Show available new articles")
            print("  python -m src.news_fetcher available 48  # Available from last 48h")
            print("  python -m src.news_fetcher history       # Show used article history")
            print("  python -m src.news_fetcher history 50    # Show last 50 entries")
            print("  python -m src.news_fetcher clear-history # Clear history")
    else:
        data = fetch_all()
        print(json.dumps(data, indent=2, default=str))
        print(f"\n[OK] Fetched {len(data['articles'])} articles (deduplicated, history-filtered)")
        if data["price"]:
            print(f"[OK] BTC Price: ${data['price']['price_usd']:,.0f} ({data['price']['change_24h']:+.2f}%)")
            print(f"[OK] Market sentiment: {data['sentiment']}")
        else:
            print("[FAIL] Could not fetch BTC price")
