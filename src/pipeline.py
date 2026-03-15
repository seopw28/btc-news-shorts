"""
Main pipeline - orchestrates the full video generation flow.

Improvements:
- Price validation: abort if BTC price fetch fails (no more $0 videos)
- Auto-switch to education content when no news articles found
- Checkpoint/resume: skip completed stages on re-run
- Article history: mark used articles to avoid repeats
- Sentiment-aware: pass market mood to script generator

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
import sys
import io
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding (cp949 -> utf-8)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.news_fetcher import fetch_all, mark_articles_used
from src.script_generator import (
    generate_script,
    generate_title_and_description,
    generate_education_script,
    generate_education_title_and_description,
    translate_script,
    translate_title_and_description,
    prepare_display_script,
)
from src.tts_generator import generate_audio
from src.video_composer import compose_video
from src.youtube_uploader import upload_video, upload_captions
from src.report_generator import generate_report
from config.settings import OUTPUT_DIR, LANGUAGES


# Checkpoint directory for resume support (in data/, not output/)
CHECKPOINT_DIR = OUTPUT_DIR.parent / "data" / "checkpoints"


def _safe_title(title: str) -> str:
    """Strip emojis and control chars but keep CJK/Korean/Japanese characters."""
    import re
    # Remove emojis (supplementary Unicode planes) and control chars, keep all scripts
    return re.sub(r'[\U00010000-\U0010ffff]', '', title).strip()


def _save_checkpoint(timestamp: str, stage: str, data: dict):
    """Save a checkpoint after completing a pipeline stage."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    cp_path = CHECKPOINT_DIR / f"cp_{timestamp}.json"

    checkpoint = {}
    if cp_path.exists():
        try:
            with open(cp_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    checkpoint[stage] = data
    checkpoint["last_stage"] = stage
    checkpoint["updated_at"] = datetime.now().isoformat()

    with open(cp_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def _load_checkpoint(timestamp: str) -> dict | None:
    """Load checkpoint for a given timestamp (for resume)."""
    cp_path = CHECKPOINT_DIR / f"cp_{timestamp}.json"
    if cp_path.exists():
        try:
            with open(cp_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _cleanup_checkpoint(timestamp: str):
    """Remove checkpoint file after successful completion."""
    cp_path = CHECKPOINT_DIR / f"cp_{timestamp}.json"
    if cp_path.exists():
        cp_path.unlink()


def _generate_for_language(
    lang: str,
    en_script: str,
    en_metadata: dict,
    news_data: dict,
    timestamp: str,
    upload: bool = False,
    checkpoint: dict = None,
) -> dict:
    """Generate TTS, video, and optionally upload for a single language."""
    lang_cfg = LANGUAGES[lang]
    lang_name = lang_cfg["name"]
    print(f"\n--- [{lang.upper()}] {lang_name} ---")

    # Check if this language was already completed (resume support)
    if checkpoint and f"lang_{lang}" in checkpoint:
        prev = checkpoint[f"lang_{lang}"]
        if prev.get("video_path") and Path(prev["video_path"]).exists():
            print(f"  [RESUME] Skipping - video already exists: {prev['video_path']}")
            return prev

    # Translate script and metadata (skip for English)
    if lang == "en":
        tts_script = en_script
        print(f"  Preparing display script for subtitles...")
        display_script = prepare_display_script(en_script)
        metadata = en_metadata
    else:
        print(f"  Translating script to {lang_name}...")
        display_script, tts_script = translate_script(en_script, lang)
        print(f"  Translating title/description to {lang_name}...")
        metadata = translate_title_and_description(en_metadata, lang)

    metadata["title"] = _safe_title(metadata["title"])
    metadata["description"] = _safe_title(metadata["description"])
    print(f"  Title: {metadata['title']}")

    # Check TTS config
    tts_engine = lang_cfg.get("tts_engine", "elevenlabs")
    google_voice = lang_cfg.get("google_voice", "")
    voice_id = lang_cfg.get("voice_id", "")

    if tts_engine == "google" and not google_voice:
        print(f"  [SKIP] No google_voice configured for {lang_name}")
        return {"lang": lang, "skipped": True, "reason": "no google_voice"}
    elif tts_engine == "elevenlabs" and not voice_id:
        print(f"  [SKIP] No voice_id configured for {lang_name}")
        return {"lang": lang, "skipped": True, "reason": "no voice_id"}

    # Generate TTS (use tts_script with spelled-out numbers)
    audio_filename = f"btc_{timestamp}_{lang}.mp3"
    print(f"  Generating TTS audio ({lang_name} via {tts_engine})...")
    audio_path = generate_audio(
        tts_script, audio_filename,
        voice_id=voice_id, tts_engine=tts_engine, google_voice=google_voice,
    )

    # Compose video (display_script for subtitles, tts_script for timing)
    video_filename = f"btc_{timestamp}_{lang}.mp4"
    print(f"  Composing video ({lang_name})...")
    price_data = news_data.get("price") if news_data else None
    fear_greed = news_data.get("fear_greed") if news_data else None
    video_path, srt_path = compose_video(
        audio_path, display_script, video_filename,
        price_data=price_data, tts_script=tts_script,
        fear_greed=fear_greed,
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

    result = {
        "lang": lang,
        "display_script": display_script,
        "tts_script": tts_script,
        "metadata": metadata,
        "audio_path": str(audio_path),
        "video_path": str(video_path),
        "video_id": video_id,
    }

    # Save per-language checkpoint
    _save_checkpoint(timestamp, f"lang_{lang}", result)
    return result


def run_pipeline(
    dry_run: bool = False,
    upload: bool = False,
    languages: list[str] = None,
    resume_timestamp: str = None,
    article_filter: str = None,
) -> dict:
    """Run the full pipeline: fetch -> script -> TTS -> video -> upload.

    Args:
        dry_run: If True, only fetch news and generate EN script.
        upload: If True, upload generated videos to YouTube.
        languages: List of language codes to generate for (default: ["en"]).
        resume_timestamp: If set, resume from checkpoint of this timestamp.
        article_filter: If set, filter articles to those containing this substring in title.
    """
    if languages is None:
        languages = ["en"]

    timestamp = resume_timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint = _load_checkpoint(timestamp) if resume_timestamp else None

    print(f"\n{'='*50}")
    print(f"  BTC News Pipeline - {timestamp}")
    if checkpoint:
        print(f"  RESUMING from checkpoint (last: {checkpoint.get('last_stage', '?')})")
    print(f"  Languages: {', '.join(lang.upper() for lang in languages)}")
    print(f"{'='*50}\n")

    # Step 1: Fetch news (or use checkpoint)
    if checkpoint and "fetch" in checkpoint:
        print("[1] Using cached news data from checkpoint...")
        news_data = checkpoint["fetch"]
    else:
        print("[1] Fetching Bitcoin news...")
        news_data = fetch_all()

        # CRITICAL: Abort if price fetch failed
        if news_data["price"] is None:
            print("\n[ABORT] Cannot proceed without BTC price data.")
            print("  -> Price API failed after retries. Please check network/API status.")
            return {"error": "price_fetch_failed", "news_data": news_data}

        print(f"  -> {len(news_data['articles'])} articles found")
        print(f"  -> BTC: ${news_data['price']['price_usd']:,.0f} ({news_data['price']['change_24h']:+.2f}%)")
        print(f"  -> Sentiment: {news_data.get('sentiment', 'N/A')}")

        # Filter to specific article if requested
        if article_filter:
            keyword = article_filter.lower()
            filtered = [a for a in news_data["articles"] if keyword in a["title"].lower()]
            if filtered:
                news_data["articles"] = filtered
                print(f"  -> Filtered to {len(filtered)} article(s) matching '{article_filter}'")
            else:
                print(f"  [WARN] No articles matching '{article_filter}', using all articles")

        _save_checkpoint(timestamp, "fetch", news_data)

    # Auto-switch to education if no articles found
    if not news_data["articles"]:
        print("\n[INFO] No new articles found. Auto-switching to education content...")
        return run_education_pipeline(upload=upload, languages=languages)

    # Step 2: Generate English script (or use checkpoint)
    if checkpoint and "script" in checkpoint:
        print("\n[2] Using cached script from checkpoint...")
        en_script = checkpoint["script"]["en_script"]
        en_metadata = checkpoint["script"]["en_metadata"]
    else:
        print("\n[2] Generating English narration script...")
        en_script = generate_script(news_data)
        word_count = len(en_script.split())
        print(f"  -> {word_count} words")
        print(f"  -> Preview: {en_script[:100]}...")

        # Step 3: Generate English metadata
        print("\n[3] Generating title & description...")
        en_metadata = generate_title_and_description(en_script)
        en_metadata["title"] = _safe_title(en_metadata["title"])
        en_metadata["description"] = _safe_title(en_metadata["description"])
        print(f"  -> Title: {en_metadata['title']}")

        _save_checkpoint(timestamp, "script", {
            "en_script": en_script, "en_metadata": en_metadata,
        })

    # Mark articles as used (so they won't appear next run)
    mark_articles_used(news_data["articles"][:5])

    if dry_run:
        print("\n[DRY RUN] Skipping TTS, video, and upload.")
        _cleanup_checkpoint(timestamp)
        return {"script": en_script, "metadata": en_metadata, "news_data": news_data}

    # Step 4: Generate per-language videos
    print(f"\n[4] Generating videos for {len(languages)} language(s)...")
    results = []
    for lang in languages:
        if lang not in LANGUAGES:
            print(f"  [SKIP] Unknown language: {lang}")
            continue
        result = _generate_for_language(
            lang, en_script, en_metadata, news_data, timestamp,
            upload=upload, checkpoint=checkpoint,
        )
        results.append(result)

    # Save run log
    log = {
        "timestamp": timestamp,
        "sentiment": news_data.get("sentiment", "unknown"),
        "en_script": en_script,
        "en_metadata": en_metadata,
        "price": news_data["price"],
        "articles_count": len(news_data["articles"]),
        "articles_used": [a["title"] for a in news_data["articles"][:5]],
        "languages": [
            {k: v for k, v in r.items() if k != "tts_script"} for r in results
        ],
    }

    log_dir = OUTPUT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{timestamp}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    # Generate PDF report for local review
    print("\n[5] Generating PDF report...")
    pdf_path = generate_report(
        news_data=news_data,
        en_script=en_script,
        en_metadata=en_metadata,
        lang_results=results,
    )

    # Cleanup checkpoint on success
    _cleanup_checkpoint(timestamp)

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
    print(f"  Report: {pdf_path}")
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
    parser.add_argument("--resume", type=str, metavar="TIMESTAMP",
                        help="Resume from checkpoint (e.g., 20260315_230000)")
    parser.add_argument("--article", type=str, metavar="KEYWORD",
                        help="Filter articles by title keyword (e.g., 'Bitwise')")
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
        run_pipeline(
            dry_run=args.dry, upload=args.upload,
            languages=languages, resume_timestamp=args.resume,
            article_filter=args.article,
        )


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
    en_metadata["description"] = _safe_title(en_metadata["description"])
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
            tts_script = en_script
            print(f"  Preparing display script for subtitles...")
            display_script = prepare_display_script(en_script)
            metadata = en_metadata
        else:
            print(f"  Translating script to {lang_name}...")
            display_script, tts_script = translate_script(en_script, lang)
            print(f"  Translating title/description to {lang_name}...")
            metadata = translate_title_and_description(en_metadata, lang)

        metadata["title"] = _safe_title(metadata["title"])
        metadata["description"] = _safe_title(metadata["description"])

        tts_engine = lang_cfg.get("tts_engine", "elevenlabs")
        google_voice = lang_cfg.get("google_voice", "")
        voice_id = lang_cfg.get("voice_id", "")

        if tts_engine == "google" and not google_voice:
            print(f"  [SKIP] No google_voice configured for {lang_name}")
            results.append({"lang": lang, "skipped": True, "reason": "no google_voice"})
            continue
        elif tts_engine == "elevenlabs" and not voice_id:
            print(f"  [SKIP] No voice_id configured for {lang_name}")
            results.append({"lang": lang, "skipped": True, "reason": "no voice_id"})
            continue

        # TTS (use tts_script with spelled-out numbers)
        audio_filename = f"btc_edu_{timestamp}_{lang}.mp3"
        print(f"  Generating TTS audio ({lang_name} via {tts_engine})...")
        audio_path = generate_audio(
            tts_script, audio_filename,
            voice_id=voice_id, tts_engine=tts_engine, google_voice=google_voice,
        )

        # Video (display_script for subtitles, tts_script for timing)
        video_filename = f"btc_edu_{timestamp}_{lang}.mp4"
        print(f"  Composing video ({lang_name})...")
        video_path, srt_path = compose_video(
            audio_path, display_script, video_filename, tts_script=tts_script,
        )

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
            "display_script": display_script,
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
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    # Generate PDF report for local review
    print("\n[4] Generating PDF report...")
    pdf_path = generate_report(
        news_data=None,
        en_script=en_script,
        en_metadata=en_metadata,
        lang_results=results,
        report_type="education",
        topic=chosen_topic,
    )

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
    print(f"  Report: {pdf_path}")
    print(f"{'='*50}\n")

    return log


if __name__ == "__main__":
    main()
