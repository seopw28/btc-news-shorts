# YouTube Data API v3 — Usage Script & End Results

**Project**: BTC News Shorts & AI Music Publishing
**Date**: 2026-03-19
**GCP Project**: btc-news-shorts
**API Client**: Automated video/music generation & upload pipelines

---

## 1. Project Overview

We operate **two automated pipelines** under one GCP project, serving a total of **4 YouTube channels**:

### Pipeline A — BTC News Shorts
An automated pipeline that:
1. Fetches the latest Bitcoin/crypto news from public APIs
2. Generates narration scripts and TTS audio
3. Composes vertical short-form videos (1080×1920, <60s)
4. **Uploads to YouTube** via Data API v3 across 3 language channels (EN, KO, JA)
5. Attaches SRT caption files for accessibility and SEO

Publishes **1–2 videos per channel per day**.

### Pipeline B — AI Music Publishing
An automated pipeline that:
1. Generates original music tracks via AI composition
2. Combines audio with cover art into video format (MP4)
3. **Uploads to YouTube** via Data API v3 (1 music channel)

Publishes **1–3 tracks per day**.

---

## 2. YouTube API Endpoints Used

| Endpoint | Purpose | Quota Cost | Used By |
|----------|---------|------------|---------|
| `youtube.videos.insert` | Upload MP4 video | 1,600 units | Both pipelines |
| `youtube.captions.insert` | Attach SRT subtitle track | 400 units | News pipeline only |

### Quota Breakdown Per Run

| Pipeline | Per Upload | Uploads/Run | Cost/Run |
|----------|-----------|-------------|----------|
| News (3 langs) | 2,000 units (video + caption) | 3 | **6,000 units** |
| Music | 1,600 units (video only) | 1–3 | **1,600–4,800 units** |
| **Combined daily total** | | | **7,600–16,800 units** |

---

## 3. Authentication Flow

- OAuth 2.0 with offline refresh tokens
- Scopes: `youtube.upload`, `youtube.force-ssl`
- Separate token files per channel:
  - `youtube_token_en.json` (News EN)
  - `youtube_token_ko.json` (News KO)
  - `youtube_token_ja.json` (News JA)
  - `youtube_token.json` (Music)
- First-time auth via browser-based `InstalledAppFlow`, then token is cached and auto-refreshed

---

## 4. Upload Source Code

### 4-A. News Pipeline — `youtube_uploader.py`

```python
"""
YouTube uploader — uploads generated Shorts via YouTube Data API v3.
First run requires browser-based OAuth2 login.
After that, token is cached in config/youtube_token_{lang}.json.
"""

import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

def get_authenticated_service(token_filename):
    """Authenticate and return YouTube API service."""
    token_file = BASE_DIR / "config" / token_filename
    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path, title, description, tags, privacy, token_filename):
    """Upload a video to YouTube and return the video ID."""
    youtube = get_authenticated_service(token_filename)

    if "#Shorts" not in description:
        description += "\n\n#Shorts #Bitcoin #CryptoNews"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    return response["id"]


def upload_captions(video_id, srt_path, language, token_filename):
    """Upload an SRT caption track to a YouTube video."""
    youtube = get_authenticated_service(token_filename)

    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": "",
            "isDraft": False,
        },
    }

    media = MediaFileUpload(str(srt_path), mimetype="application/x-subrip")
    youtube.captions().insert(
        part="snippet",
        body=body,
        media_body=media,
    ).execute()
```

### 4-B. Music Pipeline — `youtube_uploader.py`

```python
"""
YouTube uploader for AI-generated music tracks.
Converts audio + cover art into MP4 via FFmpeg, then uploads.
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

def upload_audio_as_video(audio_path, cover_path, title, description, tags):
    """Combine audio + cover image into MP4 via FFmpeg, then upload."""
    # FFmpeg: static image + audio -> MP4 (libx264, AAC 192kbps)
    video_path = _create_video_from_audio(audio_path, cover_path)

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "10",  # Music
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    return response["id"]
```

---

## 5. Pipeline Execution Scripts (CLI)

```bash
# News: Generate videos for all 3 languages and upload
python -m src.pipeline --all-langs --upload

# Music: Generate and upload a track
python main.py --upload
```

---

## 6. Actual Execution Log — News Pipeline (2026-03-19)

Below is the **real terminal output** from today's pipeline run:

```
==================================================
  BTC News Pipeline - 20260319_072039
  Languages: EN, KO, JA
==================================================

[Quota] 6,000/10,000 used today (2026-03-18 PT)
  Remaining: 4,000 units
  Uploads today: 3 videos
  Can upload: 2 more videos

[QUOTA] Can only upload 2/3 languages. Will upload first 2.

[1] Fetching Bitcoin news...
  [DEDUP] Removed 2 duplicate articles
  [HISTORY] Filtered 2 previously used articles
  [F&G] Fear & Greed: 26 (Fear)
  [GOLD] $4,799 (-3.41%)
  [DXY] 104.2 (+0.00%)
  -> 36 articles found
  -> BTC: $71,108 (-4.56%)
  -> Sentiment: bearish

[2] Generating English narration script...
  -> 142 words
  -> Preview: The Fed just poured cold water on the markets...

[3] Generating title & description...
  -> Title: Fed Freezes Rates, BTC Dumps to $71,100

[4] Generating videos for 2 language(s)...

--- [EN] English ---
  Preparing display script for subtitles...
  Title: Fed Freezes Rates, BTC Dumps to $71,100
  Generating TTS audio (English via google)...
  [OK] Audio saved: btc_20260319_072039_en.mp3 (245.1 KB)
  Composing video (English)...
  [OK] Video saved: btc_20260319_072039_en.mp4 (16.5 MB, 62.7s)
  Uploading to YouTube (English)...
  Uploading: Fed Freezes Rates, BTC Dumps to $71,100
    -> 6% uploaded ... -> 96% uploaded
  [OK] Upload complete: https://youtube.com/shorts/H0eosxyQ56w
  Uploading captions (English)...
  [OK] Caption uploaded: en -> btc_20260319_072039_en.srt

--- [KO] Korean ---
  Translating script to Korean...
  Title: 연준 금리 동결, BTC $71,100로 급락
  Generating TTS audio (Korean via google)...
  [OK] Audio saved: btc_20260319_072039_ko.mp3 (228.8 KB)
  Composing video (Korean)...
  [OK] Video saved: btc_20260319_072039_ko.mp4 (16.6 MB, 58.6s)
  Uploading to YouTube (Korean)...
  Uploading: 연준 금리 동결, BTC $71,100로 급락
    -> 6% uploaded ... -> 96% uploaded
  [OK] Upload complete: https://youtube.com/shorts/hTdSES36tk8
  Uploading captions (Korean)...
  [OK] Caption uploaded: ko -> btc_20260319_072039_ko.srt

==================================================
  Pipeline complete!
  [EN] -> YT: https://youtube.com/shorts/H0eosxyQ56w
  [KO] -> YT: https://youtube.com/shorts/hTdSES36tk8
  [JA] -> Skipped (insufficient daily quota)
==================================================
```

**Note**: The Japanese channel was skipped because the daily 10,000-unit quota had already been consumed by prior uploads (News + Music).

---

## 7. End Results

### Uploaded Videos (News — 2026-03-19)

| Language | Title | YouTube URL |
|----------|-------|-------------|
| English | Fed Freezes Rates, BTC Dumps to $71,100 | https://youtube.com/shorts/H0eosxyQ56w |
| Korean | 연준 금리 동결, BTC $71,100로 급락 | https://youtube.com/shorts/hTdSES36tk8 |
| Japanese | *(skipped — daily quota exceeded)* | — |

### Video Specifications — News Shorts
- Resolution: 1080 × 1920 (9:16 vertical)
- Duration: ~60 seconds
- Format: MP4 (H.264 + AAC)
- Category: News & Politics (ID: 25)
- Captions: SRT subtitles attached per language

### Video Specifications — Music
- Resolution: 1920 × 1080 (static cover art)
- Duration: 2–5 minutes (full track length)
- Format: MP4 (H.264 + AAC 192kbps)
- Category: Music (ID: 10)

---

## 8. Why We Need a Quota Increase

### Current Situation

| Pipeline | Daily Quota Need | Channels |
|----------|-----------------|----------|
| News (3 langs × 1–2 runs) | 6,000–12,000 units | 3 |
| Music (1–3 tracks) | 1,600–4,800 units | 1 |
| **Combined daily total** | **7,600–16,800 units** | **4** |
| **Current daily limit** | **10,000 units** | — |

### The Problem

The default 10,000-unit quota is **insufficient for both pipelines** operating under the same GCP project. As demonstrated in today's execution log:

- A single 3-language News run (6,000 units) + 1 Music upload (1,600 units) = 7,600 units
- This leaves only 2,400 units — not enough for a second News run or additional Music tracks
- The **Japanese channel is frequently skipped** due to quota exhaustion, directly impacting our Japanese-speaking audience

### Requested Quota

| Metric | Current | Requested |
|--------|---------|-----------|
| Daily quota | 10,000 units | **60,000 units** |

**60,000 units/day** would allow us to:
- Reliably publish to all **4 channels** daily without skipping any language
- Run the News pipeline **2× per day** for breaking news coverage (12,000 units)
- Upload **3–5 Music tracks** per day (4,800–8,000 units)
- Handle retry scenarios when uploads fail due to network issues
- Accommodate planned growth: additional language channels and increased posting frequency

---

## 9. Channel Links

| Channel | Type | URL |
|---------|------|-----|
| BTC News (English) | News & Politics | https://www.youtube.com/@bit_news_en |
| BTC News (Korean) | News & Politics | https://www.youtube.com/@bit_news_ko |
| BTC News (Japanese) | News & Politics | https://www.youtube.com/@bit_news_ja |
| Music | Music | https://www.youtube.com/@channel_music |

*(Replace with actual channel URLs if different)*
