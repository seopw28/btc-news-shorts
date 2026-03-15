"""
Bitcoin news fetcher - collects headlines from multiple sources.
"""

import feedparser
import requests
from datetime import datetime, timedelta


# RSS feeds for Bitcoin/crypto news
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]


def fetch_rss_news(max_age_hours: int = 24) -> list[dict]:
    """Fetch recent Bitcoin news from RSS feeds."""
    articles = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                if published and published < cutoff:
                    continue

                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", feed_url),
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            print(f"[WARN] Failed to fetch {feed_url}: {e}")

    return articles


def fetch_bitcoin_price() -> dict:
    """Fetch current Bitcoin price and 24h change from CoinGecko."""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_market_cap": "true",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()["bitcoin"]
        return {
            "price_usd": data["usd"],
            "change_24h": round(data.get("usd_24h_change", 0), 2),
            "market_cap": data.get("usd_market_cap", 0),
        }
    except Exception as e:
        print(f"[WARN] Failed to fetch BTC price: {e}")
        return {"price_usd": 0, "change_24h": 0, "market_cap": 0}


def fetch_all() -> dict:
    """Fetch all news data and price info."""
    return {
        "articles": fetch_rss_news(),
        "price": fetch_bitcoin_price(),
        "fetched_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import json
    data = fetch_all()
    print(json.dumps(data, indent=2, default=str))
    print(f"\n[OK] Fetched {len(data['articles'])} articles")
    print(f"[OK] BTC Price: ${data['price']['price_usd']:,.0f} ({data['price']['change_24h']:+.2f}%)")
