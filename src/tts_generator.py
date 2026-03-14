"""
TTS generator — converts script to speech using ElevenLabs (Hope voice).
"""

import requests
from pathlib import Path
from config.settings import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
    OUTPUT_DIR,
    TTS_STABILITY,
    TTS_SIMILARITY_BOOST,
    TTS_STYLE,
)


def generate_audio(script: str, output_filename: str = None) -> Path:
    """Generate speech audio from script text using ElevenLabs API."""
    if not output_filename:
        output_filename = "narration.mp3"

    output_path = OUTPUT_DIR / "audio" / output_filename

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"✓ Audio saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


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
