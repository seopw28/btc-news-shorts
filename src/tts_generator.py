"""
TTS generator - converts script to speech.
Supports ElevenLabs (English) and Google Cloud TTS (Korean, Japanese).
"""

import base64
import requests
from pathlib import Path
from config.settings import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
    GOOGLE_TTS_API_KEY,
    OUTPUT_DIR,
    TTS_STABILITY,
    TTS_SIMILARITY_BOOST,
    TTS_STYLE,
)


def generate_audio(
    script: str,
    output_filename: str = None,
    voice_id: str = None,
    tts_engine: str = "elevenlabs",
    google_voice: str = None,
) -> Path:
    """Generate speech audio from script text.

    Args:
        tts_engine: "elevenlabs" or "google"
        google_voice: Google Cloud TTS voice name (e.g. "ko-KR-Chirp3-HD-Autonoe")
    """
    if not output_filename:
        output_filename = "narration.mp3"

    output_path = OUTPUT_DIR / "audio" / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if tts_engine == "google":
        _generate_google_tts(script, output_path, google_voice)
    else:
        _generate_elevenlabs_tts(script, output_path, voice_id)

    print(f"[OK] Audio saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def _generate_elevenlabs_tts(script: str, output_path: Path, voice_id: str = None):
    """Generate audio using ElevenLabs API."""
    vid = voice_id or ELEVENLABS_VOICE_ID
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }

    payload = {
        "text": script,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": TTS_STABILITY,
            "similarity_boost": TTS_SIMILARITY_BOOST,
            "style": TTS_STYLE,
            "use_speaker_boost": True,
        },
    }

    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)


def _text_to_ssml(script: str) -> str:
    """Convert plain text to SSML with explicit break tags for natural pacing.
    Commas → 80ms, periods → 400ms, paragraphs → 600ms.
    """
    import re
    # Escape XML special characters
    text = script.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Paragraph breaks (double newline) → long pause
    text = re.sub(r'\n\n+', '<break time="600ms"/>', text)
    # Single newline → medium pause
    text = text.replace("\n", '<break time="300ms"/>')
    # Sentence-ending punctuation → pause after
    text = re.sub(r'([.。！？!?])\s*', r'\1<break time="400ms"/>', text)
    # Commas → short pause (but not inside numbers like 71,000)
    text = re.sub(r'(?<!\d),\s*', r',<break time="80ms"/>', text)
    # Korean/Japanese commas
    text = re.sub(r'[、，]\s*', r',<break time="80ms"/>', text)

    return f'<speak>{text}</speak>'


def _generate_google_tts(script: str, output_path: Path, voice_name: str):
    """Generate audio using Google Cloud TTS API with SSML for natural pacing."""
    parts = voice_name.split("-")
    lang_code = f"{parts[0]}-{parts[1]}"

    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_TTS_API_KEY}"

    ssml = _text_to_ssml(script)

    payload = {
        "input": {"ssml": ssml},
        "voice": {"languageCode": lang_code, "name": voice_name},
        "audioConfig": {"audioEncoding": "MP3"},
    }

    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()

    audio_bytes = base64.b64decode(response.json()["audioContent"])
    with open(output_path, "wb") as f:
        f.write(audio_bytes)


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    import subprocess

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )

    import json
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


if __name__ == "__main__":
    sample_script = (
        "Bitcoin just broke past one hundred and five thousand dollars, "
        "surging over three percent in the last twenty-four hours. "
        "This rally comes as the SEC approved a brand new crypto ETF, "
        "signaling growing institutional confidence. "
        "Stay tuned and subscribe for daily Bitcoin updates."
    )
    audio_path = generate_audio(sample_script, "test_narration.mp3")
    duration = get_audio_duration(audio_path)
    print(f"Duration: {duration:.1f}s")
