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

from config.settings import (
    YOUTUBE_CATEGORY_ID,
    YOUTUBE_PRIVACY,
    BASE_DIR,
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CLIENT_SECRET_FILE = BASE_DIR / "config" / "client_secret.json"
DEFAULT_TOKEN_FILE = BASE_DIR / "config" / "youtube_token_en.json"


def get_authenticated_service(token_filename: str = None):
    """Authenticate and return YouTube API service."""
    token_file = BASE_DIR / "config" / token_filename if token_filename else DEFAULT_TOKEN_FILE
    creds = None

    # Load cached token
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"OAuth client secret not found at {CLIENT_SECRET_FILE}\n"
                    "Download it from Google Cloud Console -> APIs -> Credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        print(f"[OK] YouTube token saved: {token_file.name}")

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] = None,
    privacy: str = None,
    token_filename: str = None,
) -> str:
    """Upload a video to YouTube and return the video ID."""
    youtube = get_authenticated_service(token_filename=token_filename)

    if tags is None:
        tags = []
    if privacy is None:
        privacy = YOUTUBE_PRIVACY

    # Add #Shorts to description for YouTube Shorts recognition
    if "#Shorts" not in description:
        description += "\n\n#Shorts #Bitcoin #CryptoNews"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": YOUTUBE_CATEGORY_ID,
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
        chunksize=1024 * 1024,  # 1MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"Uploading: {title}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  -> {int(status.progress() * 100)}% uploaded")

    video_id = response["id"]
    print(f"[OK] Upload complete: https://youtube.com/shorts/{video_id}")
    return video_id


def upload_captions(
    video_id: str,
    srt_path: Path,
    language: str = "en",
    name: str = "",
    token_filename: str = None,
) -> bool:
    """Upload an SRT caption track to a YouTube video for SEO."""
    youtube = get_authenticated_service(token_filename=token_filename)

    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": name,
            "isDraft": False,
        },
    }

    media = MediaFileUpload(str(srt_path), mimetype="application/x-subrip")

    try:
        youtube.captions().insert(
            part="snippet",
            body=body,
            media_body=media,
        ).execute()
        print(f"  [OK] Caption uploaded: {language} -> {srt_path.name}")
        return True
    except Exception as e:
        print(f"  [WARN] Caption upload failed ({language}): {e}")
        return False


if __name__ == "__main__":
    # Test: authenticate only
    service = get_authenticated_service()
    print("[OK] YouTube authentication successful")
