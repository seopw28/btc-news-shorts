"""
X (Twitter) uploader — uploads generated Shorts as video tweets via X API v2.

Authentication: OAuth 1.0a (User Context) for media upload + tweet creation.
Requires API Key, API Secret, Access Token, Access Token Secret from X Developer Portal.

Video upload uses chunked media upload (v1.1 endpoint),
then tweets with media_id via v2 tweets endpoint.
"""

import os
import time
import json
import math
from pathlib import Path

import requests
from requests_oauthlib import OAuth1

from config.settings import BASE_DIR

# --- Auth ---

def _get_oauth(lang: str = "en") -> OAuth1:
    """Build OAuth1 signer from env vars or per-language token file."""
    # Try per-language token file first
    token_file = BASE_DIR / "config" / f"x_token_{lang}.json"
    if token_file.exists():
        with open(token_file, "r") as f:
            creds = json.load(f)
        return OAuth1(
            creds["api_key"],
            creds["api_secret"],
            creds["access_token"],
            creds["access_token_secret"],
        )

    # Fallback to env vars
    api_key = os.getenv("X_API_KEY", "")
    api_secret = os.getenv("X_API_SECRET", "")
    access_token = os.getenv("X_ACCESS_TOKEN", "")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        raise ValueError(
            "X API credentials not found.\n"
            f"Either create {token_file} or set env vars:\n"
            "  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET"
        )

    return OAuth1(api_key, api_secret, access_token, access_token_secret)


# --- Chunked Media Upload (v1.1) ---

MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL = "https://api.x.com/2/tweets"
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks


def _media_init(auth: OAuth1, file_size: int, mime_type: str = "video/mp4") -> str:
    """INIT: start chunked upload, return media_id."""
    resp = requests.post(
        MEDIA_UPLOAD_URL,
        data={
            "command": "INIT",
            "total_bytes": file_size,
            "media_type": mime_type,
            "media_category": "tweet_video",
        },
        auth=auth,
    )
    resp.raise_for_status()
    media_id = resp.json()["media_id_string"]
    print(f"  [X] Media INIT: {media_id} ({file_size / 1024 / 1024:.1f} MB)")
    return media_id


def _media_append(auth: OAuth1, media_id: str, file_path: Path):
    """APPEND: upload file in chunks."""
    file_size = file_path.stat().st_size
    total_chunks = math.ceil(file_size / CHUNK_SIZE)

    with open(file_path, "rb") as f:
        for i in range(total_chunks):
            chunk = f.read(CHUNK_SIZE)
            resp = requests.post(
                MEDIA_UPLOAD_URL,
                data={
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": i,
                },
                files={"media_data": chunk},
                auth=auth,
            )
            resp.raise_for_status()
            pct = int((i + 1) / total_chunks * 100)
            print(f"  [X] Upload chunk {i + 1}/{total_chunks} ({pct}%)")


def _media_finalize(auth: OAuth1, media_id: str) -> dict:
    """FINALIZE: complete upload and wait for processing."""
    resp = requests.post(
        MEDIA_UPLOAD_URL,
        data={
            "command": "FINALIZE",
            "media_id": media_id,
        },
        auth=auth,
    )
    resp.raise_for_status()
    result = resp.json()

    # Wait for async video processing
    processing = result.get("processing_info")
    while processing and processing.get("state") in ("pending", "in_progress"):
        wait_sec = processing.get("check_after_secs", 5)
        print(f"  [X] Processing... (wait {wait_sec}s)")
        time.sleep(wait_sec)

        resp = requests.get(
            MEDIA_UPLOAD_URL,
            params={
                "command": "STATUS",
                "media_id": media_id,
            },
            auth=auth,
        )
        resp.raise_for_status()
        result = resp.json()
        processing = result.get("processing_info")

    state = processing.get("state", "succeeded") if processing else "succeeded"
    if state == "failed":
        error = processing.get("error", {})
        raise RuntimeError(f"X media processing failed: {error}")

    print(f"  [X] Media FINALIZE: {state}")
    return result


def upload_video_to_x(
    video_path: Path,
    text: str,
    lang: str = "en",
) -> str | None:
    """Upload video to X and post a tweet. Returns tweet ID or None on failure."""
    video_path = Path(video_path)
    if not video_path.exists():
        print(f"  [X][ERROR] Video not found: {video_path}")
        return None

    auth = _get_oauth(lang)
    file_size = video_path.stat().st_size

    # Step 1: Chunked media upload
    media_id = _media_init(auth, file_size)
    _media_append(auth, media_id, video_path)
    _media_finalize(auth, media_id)

    # Step 2: Post tweet with video
    payload = {
        "text": text,
        "media": {
            "media_ids": [media_id],
        },
    }

    resp = requests.post(
        TWEET_URL,
        json=payload,
        auth=auth,
    )

    if resp.status_code == 201:
        tweet_id = resp.json()["data"]["id"]
        print(f"  [X][OK] Tweet posted: https://x.com/i/status/{tweet_id}")
        return tweet_id
    else:
        print(f"  [X][ERROR] Tweet failed ({resp.status_code}): {resp.text[:200]}")
        return None


def build_tweet_text(
    title: str,
    description: str = "",
    lang: str = "en",
    tags: list[str] = None,
) -> str:
    """Build tweet text from video metadata. Max 280 chars."""
    if tags is None:
        tags = []

    # Core hashtags
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])

    # Build text: title + hashtags (fit within 280)
    text = title
    if hashtags:
        if len(text) + len(hashtags) + 2 <= 280:
            text = f"{text}\n\n{hashtags}"

    return text[:280]


if __name__ == "__main__":
    # Test: check credentials
    try:
        auth = _get_oauth()
        print("[OK] X API credentials loaded successfully")
    except ValueError as e:
        print(f"[FAIL] {e}")
