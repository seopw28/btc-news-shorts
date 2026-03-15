"""
Background video fetcher - downloads vertical stock videos from Pexels.
Falls back to local assets/backgrounds/ if no API key or download fails.
"""

import random
import requests
from pathlib import Path
from config.settings import PEXELS_API_KEY, ASSETS_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

BG_DIR = ASSETS_DIR / "backgrounds"
BG_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_QUERIES = [
    "trading screen monitor", "stock trader working", "trading chart screen",
    "cryptocurrency trading screen", "stock market trader", "trading desk monitor",
    "day trader screen", "forex trading chart",
]

CLIP_DURATION = 5  # seconds per background clip


def fetch_background_video() -> Path:
    """Download a single vertical stock video from Pexels, or use local cache."""
    cached = _get_cached_videos()
    if cached:
        choice = random.choice(cached)
        print(f"[OK] Using cached background: {choice.name}")
        return choice

    return _download_one()


def fetch_multiple_backgrounds(count: int = 12) -> list:
    """Download multiple background clips for variety. Returns list of Paths."""
    cached = _get_cached_videos()

    # If we have enough cached, use those
    if len(cached) >= count:
        selected = random.sample(cached, count)
        print(f"[OK] Using {count} cached backgrounds")
        return selected

    # Need to download more
    needed = count - len(cached)
    print(f"[...] Need {needed} more backgrounds (have {len(cached)} cached)")

    if not PEXELS_API_KEY:
        print("[WARN] No PEXELS_API_KEY - using available clips only")
        return cached if cached else []

    # Download from different search queries for variety
    queries = random.sample(SEARCH_QUERIES, min(needed, len(SEARCH_QUERIES)))
    for query in queries:
        path = _download_one(query=query)
        if path:
            cached.append(path)
        if len(cached) >= count:
            break

    # If still not enough, download more from random queries
    attempts = 0
    while len(cached) < count and attempts < 5:
        path = _download_one()
        if path and path not in cached:
            cached.append(path)
        attempts += 1

    result = cached[:count] if len(cached) >= count else cached
    random.shuffle(result)
    print(f"[OK] {len(result)} background clips ready")
    return result


def _download_one(query: str = None) -> Path:
    """Download one video from Pexels."""
    if not PEXELS_API_KEY:
        return None

    if not query:
        query = random.choice(SEARCH_QUERIES)

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query": query,
                "orientation": "portrait",
                "size": "medium",
                "per_page": 15,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        videos = data.get("videos", [])
        if not videos:
            return None

        video = random.choice(videos)
        video_file = _pick_best_file(video.get("video_files", []))
        if not video_file:
            return None

        url = video_file["link"]
        filename = f"pexels_{video['id']}.mp4"
        output_path = BG_DIR / filename

        if output_path.exists():
            print(f"  [OK] Already cached: {filename}")
            return output_path

        print(f"  [...] Downloading '{query}' ({video_file.get('width', '?')}x{video_file.get('height', '?')})...")
        dl = requests.get(url, timeout=120, stream=True)
        dl.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in dl.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  [OK] Saved: {filename} ({size_mb:.1f} MB)")
        return output_path

    except Exception as e:
        print(f"  [WARN] Download failed ({query}): {e}")
        return None


def _get_cached_videos() -> list:
    """Get list of cached background videos."""
    return list(BG_DIR.glob("*.mp4")) + list(BG_DIR.glob("*.mov"))


def _pick_best_file(files: list) -> dict:
    """Pick the best vertical video file - prefer HD, vertical orientation."""
    candidates = []
    for f in files:
        w = f.get("width", 0)
        h = f.get("height", 0)
        if h >= w and h >= 720:
            candidates.append(f)

    if not candidates:
        candidates = [f for f in files if f.get("height", 0) >= 720]
    if not candidates:
        candidates = files
    if not candidates:
        return None

    candidates.sort(key=lambda f: abs(f.get("height", 0) - VIDEO_HEIGHT))
    return candidates[0]


if __name__ == "__main__":
    clips = fetch_multiple_backgrounds(6)
    print(f"\nGot {len(clips)} clips:")
    for c in clips:
        print(f"  - {c.name}")
