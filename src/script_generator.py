"""
AI script generator — turns raw news into a 60-second narration script.
"""

from openai import OpenAI
from config.settings import OPENAI_API_KEY, OPENAI_MODEL, SCRIPT_MAX_WORDS, SCRIPT_TONE

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = f"""You are a professional Bitcoin news anchor for YouTube Shorts.
Your job is to write a narration script that is:
- Exactly under {SCRIPT_MAX_WORDS} words (this is critical for timing)
- Tone: {SCRIPT_TONE}
- Start with a strong hook (first 3 seconds matter most)
- Include the current BTC price and 24h change
- Summarize the top 1-2 most important news stories
- End with a brief call-to-action (subscribe/like)
- Do NOT use hashtags, emojis, or markdown formatting
- Write as spoken word — natural, conversational English
- Use short sentences for punchiness

Output ONLY the narration script, nothing else."""


def generate_script(news_data: dict) -> str:
    """Generate a narration script from fetched news data."""
    price = news_data["price"]
    articles = news_data["articles"][:5]  # top 5 articles

    # Build context for the AI
    news_context = f"BTC Price: ${price['price_usd']:,.0f} | 24h Change: {price['change_24h']:+.2f}%\n\n"
    news_context += "Top Headlines:\n"
    for i, article in enumerate(articles, 1):
        news_context += f"{i}. [{article['source']}] {article['title']}\n"
        if article.get("summary"):
            summary = article["summary"][:200]
            news_context += f"   Summary: {summary}\n"

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Write today's Bitcoin news script based on:\n\n{news_context}"},
        ],
        temperature=0.7,
        max_tokens=500,
    )

    script = response.choices[0].message.content.strip()
    return script


def generate_title_and_description(script: str) -> dict:
    """Generate YouTube title and description from the script."""
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": (
                "Generate a YouTube Shorts title and description for a Bitcoin news video. "
                "Title: catchy, under 60 chars, include BTC price if mentioned. "
                "Description: 2-3 sentences + relevant hashtags. "
                "Return as:\nTITLE: ...\nDESCRIPTION: ..."
            )},
            {"role": "user", "content": script},
        ],
        temperature=0.7,
        max_tokens=200,
    )

    text = response.choices[0].message.content.strip()
    title = ""
    description = ""

    for line in text.split("\n"):
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("DESCRIPTION:"):
            description = line.replace("DESCRIPTION:", "").strip()

    return {"title": title, "description": description}


if __name__ == "__main__":
    # Test with sample data
    sample = {
        "price": {"price_usd": 105000, "change_24h": 3.5, "market_cap": 2000000000000},
        "articles": [
            {"title": "Bitcoin Hits New All-Time High", "summary": "BTC surges past $105K", "source": "CoinDesk"},
            {"title": "SEC Approves New Crypto ETF", "summary": "Major regulatory milestone", "source": "CoinTelegraph"},
        ],
    }
    script = generate_script(sample)
    print("=== SCRIPT ===")
    print(script)
    print(f"\nWord count: {len(script.split())}")

    meta = generate_title_and_description(script)
    print(f"\n=== METADATA ===")
    print(f"Title: {meta['title']}")
    print(f"Description: {meta['description']}")
