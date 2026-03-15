import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Paths ===
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATES_DIR = BASE_DIR / "templates"

# === ElevenLabs ===
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# === Google Gemini ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# === Google Cloud TTS ===
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", GEMINI_API_KEY)  # fallback to Gemini key

# === Pexels (free stock video) ===
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# === Video Settings ===
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920  # 9:16 vertical (Shorts)
VIDEO_FPS = 30
MAX_DURATION_SEC = 59  # YouTube Shorts limit

# === TTS Settings ===
TTS_STABILITY = 0.5
TTS_SIMILARITY_BOOST = 0.75
TTS_STYLE = 0.3

# === Script Generation ===
SCRIPT_MAX_WORDS = 110  # ~45 seconds of speech
SCRIPT_TONE = "professional, concise, engaging"
SCRIPT_LANGUAGE = "English"

# === Fonts & Styling ===
SUBTITLE_FONT_SIZE = 48
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_BG_COLOR = "black@0.6"
SUBTITLE_POSITION = "center"

# === YouTube ===
YOUTUBE_CATEGORY_ID = "25"  # News & Politics
YOUTUBE_PRIVACY = "public"

# === Multi-language Channels ===
LANGUAGES = {
    "en": {
        "name": "English",
        "tts_engine": "google",
        "google_voice": "en-US-Chirp3-HD-Achird",
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID"),  # Daniel (fallback)
        "youtube_channel_id": "UCxTQrx4PqaQ10m_kVZdKFcA",  # bit_news
        "youtube_token": "youtube_token_en.json",
        "tags": ["bitcoin", "crypto", "btc", "cryptocurrency", "bitcoin news", "crypto news"],
        "max_words": 130,
    },
    "ko": {
        "name": "Korean",
        "tts_engine": "google",
        "google_voice": "ko-KR-Chirp3-HD-Autonoe",
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID_KO", ""),
        "youtube_channel_id": os.getenv("YOUTUBE_CHANNEL_ID_KO", ""),
        "youtube_token": "youtube_token_ko.json",
        "tags": ["비트코인", "암호화폐", "비트코인뉴스", "크립토", "BTC", "코인뉴스"],
        "max_words": 100,
    },
    "ja": {
        "name": "Japanese",
        "tts_engine": "google",
        "google_voice": "ja-JP-Chirp3-HD-Despina",
        "voice_id": os.getenv("ELEVENLABS_VOICE_ID_JA", ""),
        "youtube_channel_id": os.getenv("YOUTUBE_CHANNEL_ID_JA", ""),
        "youtube_token": "youtube_token_ja.json",
        "tags": ["ビットコイン", "仮想通貨", "暗号資産", "BTC", "ビットコインニュース"],
        "max_words": 100,
    },
}
