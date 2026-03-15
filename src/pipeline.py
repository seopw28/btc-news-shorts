"""
Main pipeline - orchestrates the full video generation flow.

Usage:
    python -m src.pipeline                          # News video, EN only
    python -m src.pipeline --upload                 # News + upload to YouTube
    python -m src.pipeline --all-langs --upload      # News for EN, KO, JA + upload
    python -m src.pipeline --lang ko                # News for specific language
    python -m src.pipeline --education              # Random BTC education topic
    python -m src.pipeline --education --topic "What is Bitcoin mining?"
    python -m src.pipeline --education --all-langs  # Education for all languages
    python -m src.pipeline --dry                    # Dry run (fetch + script only)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.news_fetcher import fetch_all
from src.script_generator import (
    generate_script,
    generate_title_and_description,
    generate_education_script,
    generate_education_title_and_description,
    translate_script,
    translate_title_and_description,
)
from src.tts_generator import generate_audio
from src.video_composer import compose_video
from src.youtube_uploader import upload_video, upload_captions
from config.settings import OUTPUT_DIR, LANGUAGES


def _safe_title(title: str) -> str:
    """Strip non-ASCII chars (emoji etc.) to avoid cp949 encoding errors on Windows."""
    return title.encode("ascii", "ignore").decode("ascii").strip()


def _generate_for_language(
    lang: str,
    en_script: str,
    en_metadata: dict,
    news_data: dict,
    timestamp: str,
    upload: bool = False,
) -> dict:
    """Generate TTS, video, and optionally upload for a single language."""
    lang_cfg = LANGUAGES[lang]
    lang_name = lang_cfg["name"]
    print(f"\n--- [{lang.upper()}] {lang_name} ---")

    # Translate script and metadata (skip for English)
    if lang == "en":
        script = en_script
        metadata = en_metadata
    else:
        print(f"  Translating script to {lang_name}...")
        script = translate_script(en_script, lang)
        print(f"  Translating title/description to {lang_name}...")
        metadata = translate_title_and_description(en_metadata, lang)

    metadata["title"] = _safe_title(metadata["title"])
    metadata["description"] = metadata["description"].encode("ascii", "ignore").decode("ascii").strip()
    print(f"  Title: {metadata['title']}")

    # Check voice_id
    voice_id = lang_cfg.get("voice_id", "")
    if not voice_id:
        print(f"  [SKIP] No voice_id configured for {lang_name}")
        return {"lang": lang, "skipped": True, "reason": "no voice_id"}

    # Generate TTS
    audio_filename = f"btc_{timestamp}_{lang}.mp3"
    print(f"  Generating TTS audio ({lang_name})...")
    audio_path = generate_audio(script, audio_filename, voice_id=voice_id)

    # Compose video
    video_filename = f"btc_{timestamp}_{lang}.mp4"
    print(f"  Composing video ({lang_name})...")
    video_path, srt_path = compose_video(
        audio_path, script, video_filename, price_data=news_data["price"]
    )

    # Upload
    video_id = None
    if upload:
        token_file = lang_cfg.get("youtube_token", "")
        if not token_file:
            print(f"  [SKIP] No youtube_token configured for {lang_name}")
        else:
            print(f"  Uploading to YouTube ({lang_name})...")
            video_id = upload_video(
                video_path=video_path,
                title=metadata["title"],
                description=metadata["description"],
                tags=lang_cfg.get("tags", []),
                token_filename=token_file,
            )
            # Upload SRT captions for SEO
            if video_id and srt_path and srt_path.exists():
                print(f"  Uploading captions ({lang_name})...")
                upload_captions(
                    video_id=video_id,
                    srt_path=srt_path,
                    language=lang,
                    token_filename=token_file,
                )

    return {
        "lang": lang,
        "script": script,
        "metadata": metadata,
        "audio_path": str(audio_path),
        "video_path": str(video_path),
        "video_id": video_id,
    }


def run_pipeline(
    dry_run: bool = False,
    upload: bool = False,
    languages: list[str] = None,
) -> dict:
    """Run the full pipeline: fetch -> script -> TTS -> video -> upload.

    Args:
        dry_run: If True, only fetch news and generate EN script.
        upload: If True, upload generated videos to YouTube.
        languages: List of language codes to generate for (default: ["en"]).
    """
    if languages is None:
        languages = ["en"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*50}")
    print(f"  BTC News Pipeline - {timestamp}")
    print(f"  Languages: {', '.join(lang.upper() for lang in languages)}")
    print(f"{'='*50}\n")

    # Step 1: Fetch news
    print("[1] Fetching Bitcoin news...")
    news_data = fetch_all()
    print(f"  -> {len(news_data['articles'])} articles found")
    print(f"  -> BTC: ${news_data['price']['price_usd']:,.0f} ({news_data['price']['change_24h']:+.2f}%)")

    # Step 2: Generate English script (base for all languages)
    print("\n[2] Generating English narration script...")
    en_script = generate_script(news_data)
    word_count = len(en_script.split())
    print(f"  -> {word_count} words")
    print(f"  -> Preview: {en_script[:100]}...")

    # Step 3: Generate English metadata
    print("\n[3] Generating title & description...")
    en_metadata = generate_title_and_description(en_script)
    en_metadata["title"] = _safe_title(en_metadata["title"])
    en_metadata["description"] = en_metadata["description"].encode("ascii", "ignore").decode("ascii").strip()
    print(f"  -> Title: {en_metadata['title']}")

    if dry_run:
        print("\n[DRY RUN] Skipping TTS, video, and upload.")
        return {"script": en_script, "metadata": en_metadata, "news_data": news_data}

    # Step 4: Generate per-language videos
    print(f"\n[4] Generating videos for {len(languages)} language(s)...")
    results = []
    for lang in languages:
        if lang not in LANGUAGES:
            print(f"  [SKIP] Unknown language: {lang}")
            continue
        result = _generate_for_language(
            lang, en_script, en_metadata, news_data, timestamp, upload=upload
        )
        results.append(result)

    # Save run log
    log = {
        "timestamp": timestamp,
        "en_script": en_script,
        "en_metadata": en_metadata,
        "price": news_data["price"],
        "articles_count": len(news_data["articles"]),
        "languages": results,
    }

    log_dir = OUTPUT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{timestamp}.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  Pipeline complete!")
    for r in results:
        if r.get("skipped"):
            print(f"  [{r['lang'].upper()}] Skipped: {r.get('reason')}")
        else:
            print(f"  [{r['lang'].upper()}] {r.get('video_path', 'N/A')}")
            if r.get("video_id"):
                print(f"         -> https://youtube.com/shorts/{r['video_id']}")
    print(f"  Log: {log_path}")
    print(f"{'='*50}\n")

    return log


def main():
    parser = argparse.ArgumentParser(description="BTC News YouTube Shorts Pipeline")
    parser.add_argument("--dry", action="store_true", help="Dry run (no TTS/video)")
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube")
    parser.add_argument("--lang", type=str, help="Single language code (en, ko, ja)")
    parser.add_argument("--all-langs", action="store_true", help="Generate for all languages (en, ko, ja)")
    parser.add_argument("--education", action="store_true", help="Generate education content instead of news")
    parser.add_argument("--topic", type=str, help="Specific education topic (with --education)")
    args = parser.parse_args()

    if args.all_langs:
        languages = list(LANGUAGES.keys())
    elif args.lang:
        languages = [args.lang]
    else:
        languages = ["en"]

    if args.education:
        run_education_pipeline(topic=args.topic, upload=args.upload, languages=languages)
    else:
        run_pipeline(dry_run=args.dry, upload=args.upload, languages=languages)


def run_education_pipeline(
    topic: str = None,
    upload: bool = False,
    languages: list[str] = None,
) -> dict:
    """Run the education pipeline: generate topic script -> TTS -> video -> upload.

    Unlike the news pipeline, this doesn't fetch news data.
    Background videos are still used, but no price overlay.
    """
    if languages is None:
        languages = ["en"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*50}")
    print(f"  BTC Education Pipeline - {timestamp}")
    print(f"  Languages: {', '.join(lang.upper() for lang in languages)}")
    print(f"{'='*50}\n")

    # Step 1: Generate education script
    print("[1] Generating education script...")
    en_script, chosen_topic = generate_education_script(topic)
    word_count = len(en_script.split())
    print(f"  -> Topic: {chosen_topic}")
    print(f"  -> {word_count} words")
    print(f"  -> Preview: {en_script[:100]}...")

    # Step 2: Generate metadata
    print("\n[2] Generating title & description...")
    en_metadata = generate_education_title_and_description(en_script, chosen_topic)
    en_metadata["title"] = _safe_title(en_metadata["title"])
    en_metadata["description"] = en_metadata["description"].encode("ascii", "ignore").decode("ascii").strip()
    print(f"  -> Title: {en_metadata['title']}")

    # Step 3: Generate per-language videos (no price overlay)
    print(f"\n[3] Generating videos for {len(languages)} language(s)...")
    results = []
    for lang in languages:
        if lang not in LANGUAGES:
            print(f"  [SKIP] Unknown language: {lang}")
            continue

        lang_cfg = LANGUAGES[lang]
        lang_name = lang_cfg["name"]
        print(f"\n--- [{lang.upper()}] {lang_name} ---")

        if lang == "en":
            script = en_script
            metadata = en_metadata
        else:
            print(f"  Translating script to {lang_name}...")
            script = translate_script(en_script, lang)
            print(f"  Translating title/description to {lang_name}...")
            metadata = translate_title_and_description(en_metadata, lang)

        metadata["title"] = _safe_title(metadata["title"])
        metadata["description"] = metadata["description"].encode("ascii", "ignore").decode("ascii").strip()

        voice_id = lang_cfg.get("voice_id", "")
        if not voice_id:
            print(f"  [SKIP] No voice_id configured for {lang_name}")
            results.append({"lang": lang, "skipped": True, "reason": "no voice_id"})
            continue

        # TTS
        audio_filename = f"btc_edu_{timestamp}_{lang}.mp3"
        print(f"  Generating TTS audio ({lang_name})...")
        audio_path = generate_audio(script, audio_filename, voice_id=voice_id)

        # Video (no price_data for education)
        video_filename = f"btc_edu_{timestamp}_{lang}.mp4"
        print(f"  Composing video ({lang_name})...")
        video_path, srt_path = compose_video(audio_path, script, video_filename)

        # Upload
        video_id = None
        if upload:
            token_file = lang_cfg.get("youtube_token", "")
            if token_file:
                print(f"  Uploading to YouTube ({lang_name})...")
                video_id = upload_video(
                    video_path=video_path,
                    title=metadata["title"],
                    description=metadata["description"],
                    tags=lang_cfg.get("tags", []),
                    token_filename=token_file,
                )
                if video_id and srt_path and srt_path.exists():
                    print(f"  Uploading captions ({lang_name})...")
                    upload_captions(
                        video_id=video_id,
                        srt_path=srt_path,
                        language=lang,
                        token_filename=token_file,
                    )

        results.append({
            "lang": lang,
            "script": script,
            "metadata": metadata,
            "audio_path": str(audio_path),
            "video_path": str(video_path),
            "video_id": video_id,
        })

    # Save log
    log = {
        "timestamp": timestamp,
        "type": "education",
        "topic": chosen_topic,
        "en_script": en_script,
        "en_metadata": en_metadata,
        "languages": results,
    }

    log_dir = OUTPUT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"edu_{timestamp}.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  Education pipeline complete!")
    print(f"  Topic: {chosen_topic}")
    for r in results:
        if r.get("skipped"):
            print(f"  [{r['lang'].upper()}] Skipped: {r.get('reason')}")
        else:
            print(f"  [{r['lang'].upper()}] {r.get('video_path', 'N/A')}")
            if r.get("video_id"):
                print(f"         -> https://youtube.com/shorts/{r['video_id']}")
    print(f"  Log: {log_path}")
    print(f"{'='*50}\n")

    return log


if __name__ == "__main__":
    main()
