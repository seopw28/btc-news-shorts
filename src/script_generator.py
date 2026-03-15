"""
AI script generator - turns raw news into a 60-second narration script.
Uses Google Gemini API via REST.
"""

import requests
from config.settings import GEMINI_API_KEY, SCRIPT_MAX_WORDS, SCRIPT_TONE

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

SYSTEM_PROMPT = f"""You are a professional Bitcoin news anchor for YouTube Shorts.
Your job is to write a narration script that is:
- Exactly under {SCRIPT_MAX_WORDS} words (this is critical for timing)
- Tone: {SCRIPT_TONE}
- Start with a strong hook (first 3 seconds matter most)
- Include the current BTC price and 24h change
- Summarize the top 1-2 most important news stories
- End with a brief call-to-action (subscribe/like)
- Do NOT use hashtags, emojis, or markdown formatting
- Write as spoken word - natural, conversational English
- Use short sentences for punchiness

Output ONLY the narration script, nothing else."""


def _call_gemini(prompt: str, max_tokens: int = 2000) -> str:
    """Call Gemini API via REST."""
    resp = requests.post(
        GEMINI_URL,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": max_tokens,
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate_script(news_data: dict) -> str:
    """Generate a narration script from fetched news data."""
    price = news_data["price"]
    articles = news_data["articles"][:5]

    news_context = f"BTC Price: ${price['price_usd']:,.0f} | 24h Change: {price['change_24h']:+.2f}%\n\n"
    news_context += "Top Headlines:\n"
    for i, article in enumerate(articles, 1):
        news_context += f"{i}. [{article['source']}] {article['title']}\n"
        if article.get("summary"):
            summary = article["summary"][:200]
            news_context += f"   Summary: {summary}\n"

    prompt = f"{SYSTEM_PROMPT}\n\nWrite today's Bitcoin news script based on:\n\n{news_context}"
    return _call_gemini(prompt)


def generate_title_and_description(script: str) -> dict:
    """Generate YouTube title and description from the script."""
    prompt = (
        "Generate a YouTube Shorts title and description for a Bitcoin news video.\n"
        "Rules:\n"
        "- Title: catchy, under 60 chars, include BTC price if mentioned\n"
        "- Description: 2-3 sentences + relevant hashtags\n"
        "- Use EXACTLY this format (each on its own line):\n"
        "TITLE: your title here\n"
        "DESCRIPTION: your description here\n\n"
        f"Script:\n{script}"
    )

    text = _call_gemini(prompt)
    title = ""
    description = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("TITLE:"):
            title = line[6:].strip().strip("*")
        elif line.upper().startswith("DESCRIPTION:"):
            description = line[12:].strip().strip("*")

    # Fallback if parsing failed
    if not title:
        title = "Bitcoin News Today - Daily BTC Update"
    if not description:
        description = "Your daily Bitcoin news update. #Bitcoin #BTC #CryptoNews"

    return {"title": title, "description": description}


def translate_script(script: str, target_lang: str) -> str:
    """Translate a script to another language, keeping it natural for TTS."""
    lang_names = {"ko": "Korean", "ja": "Japanese", "en": "English"}
    lang_name = lang_names.get(target_lang, target_lang)

    prompt = (
        f"Translate this Bitcoin news narration script to {lang_name}.\n"
        f"Rules:\n"
        f"- Keep it natural and conversational for voice narration (TTS)\n"
        f"- Maintain the same tone and energy\n"
        f"- Keep numbers and BTC price as-is (e.g. $71,000)\n"
        f"- Do NOT add any formatting, hashtags, or emojis\n"
        f"- Output ONLY the translated script, nothing else\n\n"
        f"Script:\n{script}"
    )
    return _call_gemini(prompt)


EDUCATION_PROMPT = f"""You are a Bitcoin educator creating YouTube Shorts scripts.
Your job is to write a narration script that is:
- Exactly under {SCRIPT_MAX_WORDS} words (critical for timing)
- Tone: {SCRIPT_TONE}, but also educational and easy to understand
- Start with a curiosity-provoking hook (first 3 seconds matter most)
- Explain the topic simply - assume the viewer knows nothing
- Use analogies and real-world comparisons when helpful
- End with a brief call-to-action (subscribe/like for more)
- Do NOT use hashtags, emojis, or markdown formatting
- Write as spoken word - natural, conversational English
- Use short sentences for punchiness

Output ONLY the narration script, nothing else."""

EDUCATION_TOPICS = [
    "What is Bitcoin and how does it work?",
    "What is blockchain technology?",
    "What is Bitcoin mining and why does it matter?",
    "What is the Bitcoin halving and why does the price change?",
    "What are Bitcoin wallets - hot vs cold storage?",
    "What is a Bitcoin ETF and why is it important?",
    "Bitcoin vs gold - which is a better store of value?",
    "What is the Lightning Network and how does it make Bitcoin faster?",
    "Why is Bitcoin limited to 21 million coins?",
    "What is proof of work and why does Bitcoin use it?",
    "What are Bitcoin transaction fees and how do they work?",
    "What is a Bitcoin node and why should you run one?",
    "What is the difference between Bitcoin and altcoins?",
    "How does Bitcoin protect against inflation?",
    "What is a seed phrase and why is it so important?",
    "What is DCA (Dollar Cost Averaging) for Bitcoin?",
    "Who is Satoshi Nakamoto?",
    "What is a 51% attack on Bitcoin?",
    "How does Bitcoin privacy work - is it really anonymous?",
    "What is the mempool and how do Bitcoin transactions get confirmed?",
]


def generate_education_script(topic: str = None) -> tuple[str, str]:
    """Generate an educational script about a Bitcoin topic.
    Returns (script, topic) tuple.
    """
    if not topic:
        import random
        topic = random.choice(EDUCATION_TOPICS)

    prompt = f"{EDUCATION_PROMPT}\n\nTopic: {topic}"
    script = _call_gemini(prompt)
    return script, topic


def generate_education_title_and_description(script: str, topic: str) -> dict:
    """Generate YouTube title and description for an educational Bitcoin video."""
    prompt = (
        "Generate a YouTube Shorts title and description for a Bitcoin educational video.\n"
        "Rules:\n"
        "- Title: catchy, under 60 chars, make people curious\n"
        "- Description: 2-3 sentences explaining what they'll learn + relevant hashtags\n"
        "- Use EXACTLY this format (each on its own line):\n"
        "TITLE: your title here\n"
        "DESCRIPTION: your description here\n\n"
        f"Topic: {topic}\n"
        f"Script:\n{script}"
    )

    text = _call_gemini(prompt)
    title = ""
    description = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("TITLE:"):
            title = line[6:].strip().strip("*")
        elif line.upper().startswith("DESCRIPTION:"):
            description = line[12:].strip().strip("*")

    if not title:
        title = f"Bitcoin Explained - {topic[:40]}"
    if not description:
        description = f"Learn about {topic}. #Bitcoin #BTC #CryptoEducation"

    return {"title": title, "description": description}


def translate_title_and_description(metadata: dict, target_lang: str) -> dict:
    """Translate title and description to another language."""
    lang_names = {"ko": "Korean", "ja": "Japanese", "en": "English"}
    lang_name = lang_names.get(target_lang, target_lang)

    prompt = (
        f"Translate this YouTube Shorts title and description to {lang_name}.\n"
        f"Rules:\n"
        f"- Title: catchy, under 60 chars, keep BTC price\n"
        f"- Description: natural, include hashtags in {lang_name}\n"
        f"- Use EXACTLY this format:\n"
        f"TITLE: translated title\n"
        f"DESCRIPTION: translated description\n\n"
        f"Title: {metadata['title']}\n"
        f"Description: {metadata['description']}"
    )

    text = _call_gemini(prompt)
    title = ""
    description = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("TITLE:"):
            title = line[6:].strip().strip("*")
        elif line.upper().startswith("DESCRIPTION:"):
            description = line[12:].strip().strip("*")

    return {
        "title": title or metadata["title"],
        "description": description or metadata["description"],
    }


if __name__ == "__main__":
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
