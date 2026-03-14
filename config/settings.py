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

# === OpenAI ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

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
SCRIPT_MAX_WORDS = 130  # ~60 seconds of speech
SCRIPT_TONE = "professional, concise, engaging"
SCRIPT_LANGUAGE = "English"

# === Fonts & Styling ===
SUBTITLE_FONT_SIZE = 48
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_BG_COLOR = "black@0.6"
SUBTITLE_POSITION = "center"

# === YouTube ===
YOUTUBE_CATEGORY_ID = "25"  # News & Politics
YOUTUBE_TAGS = ["bitcoin", "crypto", "btc", "cryptocurrency", "bitcoin news", "crypto news"]
YOUTUBE_PRIVACY = "public"
