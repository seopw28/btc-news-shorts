"""
AI script generator - turns raw news into a 60-second narration script.
Uses Claude CLI for local runs, with Gemini as fallback for CI/scheduled runs.

Improvements:
- Market sentiment-aware tone (surge/crash/sideways → different energy)
- LLM output validation + retry for dual-script markers
- Translation length validation + re-request if exceeded
- HTML-clean summaries support
"""

import os
import subprocess
import shutil
import requests
from config.settings import GEMINI_API_KEY, SCRIPT_MAX_WORDS, SCRIPT_TONE

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Max retries for LLM output validation
MAX_LLM_RETRIES = 2

# Sentiment-specific tone instructions
SENTIMENT_TONES = {
    "surge": (
        "The market is SURGING. Match this energy:\n"
        "- Open with excitement and urgency\n"
        "- Use power words: 'explodes', 'rockets', 'breaks through'\n"
        "- Convey FOMO but stay factual\n"
        "- Fast-paced delivery, short punchy sentences"
    ),
    "crash": (
        "The market is CRASHING. Match this energy:\n"
        "- Open with urgency and gravity\n"
        "- Use strong words: 'plunges', 'crashes', 'wipes out'\n"
        "- Stay calm but convey the seriousness\n"
        "- Include brief perspective (is this a buying opportunity?)"
    ),
    "bullish": (
        "The market is trending UP. Tone:\n"
        "- Confident, optimistic but measured\n"
        "- Highlight the positive momentum\n"
        "- Keep energy moderately high"
    ),
    "bearish": (
        "The market is trending DOWN. Tone:\n"
        "- Serious but not panicked\n"
        "- Analytical, focus on why\n"
        "- End with forward-looking perspective"
    ),
    "sideways": (
        "The market is SIDEWAYS. Tone:\n"
        "- Focus on the most interesting NEWS story instead of price\n"
        "- Keep it engaging despite low volatility\n"
        "- Find the narrative hook in non-price events"
    ),
}


def _build_system_prompt(sentiment: str = "sideways") -> str:
    """Build system prompt with sentiment-aware tone."""
    tone_instruction = SENTIMENT_TONES.get(sentiment, SENTIMENT_TONES["sideways"])

    return f"""You are a professional Bitcoin news anchor for YouTube Shorts.
Your job is to write a narration script that is:
- STRICTLY under {SCRIPT_MAX_WORDS} words / under 700 characters (this is critical - aim for 45 seconds of speech)
- Tone: {SCRIPT_TONE}
- STRUCTURE (4-part, this is critical):
  PART 1 - HOOK (1 sentence, first 2 seconds):
     ONE bold, punchy headline that captures the core takeaway.
     This must hit hard. Examples:
     "Whales just bought two billion dollars of Bitcoin in 24 hours."
     "The SEC just changed everything for crypto."
     "Bitcoin is about to break its all-time high."
  PART 2 - KEY NEWS (2-3 sentences, ~15 seconds):
     BTC price, 24h change, and the headline story.
  PART 3 - WHY IT MATTERS (2-3 sentences, ~20 seconds):
     Analysis, context, what this means for the market.
  PART 4 - OUTLOOK + CTA (1-2 sentences, ~8 seconds):
     Brief outlook and call-to-action (subscribe/like).
- Include the current BTC price and 24h change
- Summarize the top 1-2 most important news stories
- Do NOT use hashtags, emojis, or markdown formatting
- Write as spoken word - natural, conversational English
- Use short sentences for punchiness
- Target total duration: 45 seconds (NOT 60 seconds)

{tone_instruction}

Output ONLY the narration script, nothing else."""


# Keep original for backward compat
SYSTEM_PROMPT = _build_system_prompt("sideways")


def _call_claude_cli(prompt: str, system: str = None) -> str:
    """Call Claude via local CLI (uses Claude Code subscription, no API key needed)."""
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)  # allow nested invocation
    # Ensure git-bash is findable on Windows
    if os.name == "nt" and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
        for bash_path in [
            os.path.join(os.path.dirname(shutil.which("git") or ""), "..", "bin", "bash.exe"),
            r"D:\D_program\Git\bin\bash.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if os.path.isfile(bash_path):
                env["CLAUDE_CODE_GIT_BASH_PATH"] = os.path.abspath(bash_path)
                break
    result = subprocess.run(
        ["claude", "-p", full_prompt],
        capture_output=True, text=True, timeout=120, env=env,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr[:500]}")
    return result.stdout.strip()


def _call_gemini(prompt: str, max_tokens: int = 8000) -> str:
    """Call Gemini API via REST (fallback for CI/scheduled runs)."""
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


def _call_llm(prompt: str, system: str = None, max_tokens: int = 2000) -> str:
    """Call the best available LLM. Prefers Claude CLI (local), falls back to Gemini API."""
    if shutil.which("claude"):
        return _call_claude_cli(prompt, system=system)
    return _call_gemini(f"{system}\n\n{prompt}" if system else prompt, max_tokens=max_tokens)


def generate_script(news_data: dict) -> str:
    """Generate a narration script from fetched news data.
    Uses market sentiment to adjust tone and energy.
    """
    price = news_data["price"]
    articles = news_data["articles"][:5]
    sentiment = news_data.get("sentiment", "sideways")

    news_context = f"BTC Price: ${price['price_usd']:,.0f} | 24h Change: {price['change_24h']:+.2f}%\n"
    news_context += f"Market Sentiment: {sentiment.upper()}\n\n"
    news_context += "Top Headlines:\n"
    for i, article in enumerate(articles, 1):
        news_context += f"{i}. [{article['source']}] {article['title']}\n"
        if article.get("summary"):
            summary = article["summary"][:300]
            news_context += f"   Summary: {summary}\n"

    system = _build_system_prompt(sentiment)
    user_prompt = f"Write today's Bitcoin news script based on:\n\n{news_context}"
    return _call_llm(user_prompt, system=system)


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

    text = _call_llm(prompt)
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


def _validate_dual_script(text: str) -> bool:
    """Check if LLM output contains proper ---SUBTITLE--- and ---VOICE--- markers."""
    upper = text.upper().replace(" ", "")
    return "---SUBTITLE---" in upper and "---VOICE---" in upper


def _validate_translation_length(subtitle: str, target_lang: str) -> bool:
    """Check if translation meets length constraints."""
    limits = {"ko": 500, "ja": 400}
    limit = limits.get(target_lang)
    if limit and len(subtitle) > limit:
        return False
    return True


def translate_script(script: str, target_lang: str) -> tuple[str, str]:
    """Translate a script to another language with validation and retry.
    Returns (display_script, tts_script):
      - display_script: numbers as digits ($71,835, 1.84%) for subtitles
      - tts_script: numbers spelled out for natural TTS reading
    """
    lang_names = {"ko": "Korean", "ja": "Japanese", "en": "English"}
    lang_name = lang_names.get(target_lang, target_lang)

    length_hint = {
        "ko": "- IMPORTANT: Keep under 500 characters total (for SUBTITLE version). Translate faithfully but concisely. Cut filler, do NOT expand beyond the original.\n",
        "ja": "- CRITICAL: Keep under 400 characters total (for SUBTITLE version). Aggressively shorten to about 55% of the English version. Cut all filler, combine sentences. Brevity > completeness.\n",
    }

    number_examples = {
        "ko": (
            "  SUBTITLE: 비트코인이 $71,835에 거래되고 있으며, 24시간 동안 1.84% 상승했습니다.\n"
            "  VOICE: 비트코인이 칠만 천팔백삼십오 달러에 거래되고 있으며, 이십사 시간 동안 일 점 팔사 퍼센트 상승했습니다.\n"
        ),
        "ja": (
            "  SUBTITLE: ビットコインは$71,835で取引されており、24時間で1.84%上昇しました。\n"
            "  VOICE: ビットコインは七万千八百三十五ドルで取引されており、二十四時間で一点八四パーセント上昇しました。\n"
        ),
    }

    base_prompt = (
        f"Translate this Bitcoin news narration script to {lang_name}.\n"
        f"You MUST output TWO versions:\n\n"
        f"1. SUBTITLE version: Numbers as digits ($71,835, 1.84%). Used for on-screen subtitles.\n"
        f"2. VOICE version: ALL numbers/prices/percentages spelled out in {lang_name}. Used for TTS voice.\n"
        f"   Both versions must have the same sentences, same meaning — only number formatting differs.\n\n"
        f"Rules:\n"
        f"- Keep it natural and conversational\n"
        f"- Maintain the same tone and energy\n"
        f"- Add commas at natural breathing points for pacing (every 10-15 syllables)\n"
        f"{{length_extra}}"
        f"- Do NOT add any formatting, hashtags, or emojis\n\n"
        f"Example:\n{number_examples.get(target_lang, '')}\n"
        f"Output format (use these EXACT markers on their own line):\n"
        f"---SUBTITLE---\n(translated script with digit numbers)\n---VOICE---\n(same script with spelled-out numbers)\n\n"
        f"Script:\n{script}"
    )

    for attempt in range(MAX_LLM_RETRIES + 1):
        length_extra = length_hint.get(target_lang, "")
        if attempt > 0:
            # Stronger instruction on retry
            length_extra += (
                f"- RETRY: Your previous output was too long or missing markers. "
                f"You MUST use ---SUBTITLE--- and ---VOICE--- markers. "
                f"Shorten aggressively if needed.\n"
            )

        prompt = base_prompt.replace("{length_extra}", length_extra)
        result = _call_llm(prompt)

        # Validate markers
        if not _validate_dual_script(result):
            print(f"  [WARN] Dual-script markers missing (attempt {attempt + 1}/{MAX_LLM_RETRIES + 1})")
            if attempt < MAX_LLM_RETRIES:
                continue
            # Final fallback: use whole text for both
            print(f"  [FALLBACK] Using raw text for both subtitle and voice")
            return result.strip(), result.strip()

        subtitle, voice = _parse_dual_script(result)

        # Validate length
        if not _validate_translation_length(subtitle, target_lang):
            limits = {"ko": 500, "ja": 400}
            limit = limits.get(target_lang, 0)
            print(f"  [WARN] {lang_name} subtitle too long: {len(subtitle)} chars (limit: {limit}) "
                  f"(attempt {attempt + 1}/{MAX_LLM_RETRIES + 1})")
            if attempt < MAX_LLM_RETRIES:
                continue

        return subtitle, voice

    return subtitle, voice


def prepare_display_script(tts_script: str) -> str:
    """Convert an English TTS script (spelled-out numbers) to display format (digits).
    Used for English subtitles.
    """
    prompt = (
        "Convert this narration script to subtitle display format.\n"
        "Rules:\n"
        "- Replace ALL spelled-out numbers with digits: 'seventy-one thousand eight hundred thirty-five dollars' → '$71,835'\n"
        "- Replace spelled-out percentages: 'one point eight four percent' → '1.84%'\n"
        "- Replace 'twenty-four hours' → '24 hours', 'two billion' → '$2B', 'ten million' → '$10M'\n"
        "- Keep everything else exactly the same (same sentences, same words)\n"
        "- Output ONLY the converted script, nothing else\n\n"
        f"Script:\n{tts_script}"
    )
    return _call_llm(prompt)


def _parse_dual_script(text: str) -> tuple[str, str]:
    """Parse LLM output containing ---SUBTITLE--- and ---VOICE--- sections."""
    subtitle = ""
    voice = ""
    current = None

    for line in text.split("\n"):
        stripped = line.strip()
        if "---SUBTITLE---" in stripped.upper().replace(" ", ""):
            current = "subtitle"
            continue
        elif "---VOICE---" in stripped.upper().replace(" ", ""):
            current = "voice"
            continue

        if current == "subtitle":
            subtitle += line + "\n"
        elif current == "voice":
            voice += line + "\n"

    subtitle = subtitle.strip()
    voice = voice.strip()

    # Fallback: if parsing fails, use the whole text for both
    if not subtitle or not voice:
        subtitle = text.strip()
        voice = text.strip()

    return subtitle, voice


EDUCATION_PROMPT = f"""You are a Bitcoin educator creating YouTube Shorts scripts.
Your job is to write a narration script that is:
- STRICTLY under {SCRIPT_MAX_WORDS} words / under 700 characters (aim for 45 seconds of speech)
- Tone: {SCRIPT_TONE}, but also educational and easy to understand
- STRUCTURE (4-part):
  HOOK (1 sentence, 2 seconds): ONE bold, surprising statement that stops scrolling.
     "There will only ever be twenty-one million Bitcoin. Here's why that matters."
     "Bitcoin uses more electricity than some countries. But it's not what you think."
  KEY CONCEPT (2-3 sentences, ~15 seconds): Explain the core idea simply.
  WHY IT MATTERS (2-3 sentences, ~20 seconds): Context, analogies, real-world impact.
  CTA (1 sentence, ~3 seconds): Subscribe/like for more.
- Assume the viewer knows nothing
- Do NOT use hashtags, emojis, or markdown formatting
- Write as spoken word - natural, conversational English
- Use short sentences for punchiness
- Target total duration: 45 seconds (NOT 60 seconds)

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

    user_prompt = f"Topic: {topic}"
    script = _call_llm(user_prompt, system=EDUCATION_PROMPT)
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

    text = _call_llm(prompt)
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

    text = _call_llm(prompt)
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
        "sentiment": "bullish",
    }
    script = generate_script(sample)
    print("=== SCRIPT ===")
    print(script)
    print(f"\nWord count: {len(script.split())}")

    meta = generate_title_and_description(script)
    print(f"\n=== METADATA ===")
    print(f"Title: {meta['title']}")
    print(f"Description: {meta['description']}")
