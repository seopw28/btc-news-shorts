"""
Suno API music generator — creates copyright-free background music.

Uses sunoapi.org to generate instrumental tracks for video backgrounds.
Generated music is royalty-free and safe for YouTube monetization.

Usage:
    from src.music_generator import generate_bgm
    audio_path = generate_bgm(style="lofi chill ambient electronic")
    audio_path = generate_bgm(style="dramatic orchestral news intro", duration="short")
"""

import os
import time
import requests
from pathlib import Path

from config.settings import BASE_DIR, OUTPUT_DIR

SUNO_API_KEY = os.getenv("SUNO_API_KEY", "")
SUNO_BASE_URL = "https://api.sunoapi.org"
SUNO_MODEL = "V4_5ALL"

BGM_DIR = OUTPUT_DIR / "bgm"

# Default styles for different video moods
BGM_STYLES = {
    "news": "cinematic ambient electronic, subtle tension, modern news broadcast feel, professional",
    "bullish": "upbeat electronic, energetic, optimistic, modern tech vibe, driving rhythm",
    "bearish": "dark ambient, moody, serious, minor key, subtle electronic beats",
    "education": "lofi chill, calm, soft piano with ambient pads, relaxing study music",
    "intro": "short dramatic orchestral hit, news intro, powerful brass, 5 seconds",
}


def _headers() -> dict:
    key = SUNO_API_KEY
    if not key:
        raise ValueError(
            "SUNO_API_KEY not set. Add it to .env file.\n"
            "Get your key at: https://sunoapi.org/api-key"
        )
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def generate_bgm(
    style: str = None,
    mood: str = "news",
    title: str = "BTC News BGM",
    model: str = None,
    wait: bool = True,
    max_wait_sec: int = 300,
) -> Path | None:
    """Generate an instrumental background music track.

    Args:
        style: Music style description. If None, uses mood preset.
        mood: Preset mood key (news/bullish/bearish/education/intro).
        title: Track title.
        model: Suno model version (default: V4_5ALL).
        wait: If True, poll until generation completes.
        max_wait_sec: Max seconds to wait for generation.

    Returns:
        Path to downloaded MP3 file, or None if failed.
    """
    if style is None:
        style = BGM_STYLES.get(mood, BGM_STYLES["news"])
    if model is None:
        model = SUNO_MODEL

    BGM_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Request generation
    payload = {
        "customMode": True,
        "instrumental": True,
        "model": model,
        "style": style,
        "title": title,
        "callBackUrl": "https://localhost/callback",  # Required field; we poll instead
    }

    print(f"[BGM] Generating: {style[:60]}...")
    resp = requests.post(
        f"{SUNO_BASE_URL}/api/v1/generate",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 200:
        print(f"[BGM] API error: {data.get('msg', 'unknown')}")
        return None

    task_id = data["data"]["taskId"]
    print(f"[BGM] Task created: {task_id}")

    if not wait:
        print(f"[BGM] Not waiting. Check status with task_id: {task_id}")
        return None

    # Step 2: Poll for completion
    audio_url = _poll_task(task_id, max_wait_sec)
    if not audio_url:
        return None

    # Step 3: Download the audio
    return _download_audio(audio_url, title)


def _poll_task(task_id: str, max_wait_sec: int = 300) -> str | None:
    """Poll task status until complete. Returns audio_url or None."""
    poll_url = f"{SUNO_BASE_URL}/api/v1/generate/record-info"
    start = time.time()
    interval = 10  # seconds between polls

    while time.time() - start < max_wait_sec:
        try:
            resp = requests.get(
                poll_url,
                params={"taskId": task_id},
                headers=_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()

            status = result.get("data", {}).get("status", "UNKNOWN")
            print(f"[BGM] Status: {status} ({int(time.time() - start)}s elapsed)")

            if status == "SUCCESS":
                response = result["data"].get("response", {})
                # API returns sunoData (not data)
                tracks = response.get("sunoData") or response.get("data") or []
                if tracks:
                    # Return the first track's audio URL (camelCase: audioUrl)
                    url = tracks[0].get("audioUrl") or tracks[0].get("audio_url")
                    duration = tracks[0].get("duration", 0)
                    print(f"[BGM] Generated {len(tracks)} track(s), duration: {duration:.1f}s")
                    return url
                print("[BGM] Success but no tracks returned")
                return None
            elif status == "FAILED":
                print(f"[BGM] Generation failed")
                return None
            # PENDING or GENERATING — keep polling
        except Exception as e:
            print(f"[BGM] Poll error: {e}")

        time.sleep(interval)

    print(f"[BGM] Timeout after {max_wait_sec}s")
    return None


def _download_audio(url: str, title: str) -> Path:
    """Download audio file from URL."""
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    safe_title = safe_title.replace(" ", "_")[:50]
    filename = f"bgm_{safe_title}_{int(time.time())}.mp3"
    out_path = BGM_DIR / filename

    print(f"[BGM] Downloading: {url[:80]}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(resp.content)

    size_kb = out_path.stat().st_size / 1024
    print(f"[BGM] Saved: {out_path} ({size_kb:.1f} KB)")
    return out_path


def get_credits() -> dict | None:
    """Check remaining Suno API credits."""
    try:
        resp = requests.get(
            f"{SUNO_BASE_URL}/api/v1/generate/credit",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception as e:
        print(f"[BGM] Credit check failed: {e}")
        return None


if __name__ == "__main__":
    # Test: generate a news-style BGM
    print("=== Suno BGM Generator Test ===")
    credits = get_credits()
    if credits:
        print(f"Credits remaining: {credits}")
    path = generate_bgm(mood="news", title="BTC Daily News BGM")
    if path:
        print(f"\nSuccess: {path}")
    else:
        print("\nFailed to generate BGM")
