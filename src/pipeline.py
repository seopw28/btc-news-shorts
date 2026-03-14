"""
Main pipeline — orchestrates the full video generation flow.

Usage:
    python -m src.pipeline          # Generate one video
    python -m src.pipeline --dry    # Dry run (fetch + script only, no video)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.news_fetcher import fetch_all
from src.script_generator import generate_script, generate_title_and_description
from src.tts_generator import generate_audio
from src.video_composer import compose_video
from config.settings import OUTPUT_DIR


def run_pipeline(dry_run: bool = False) -> dict:
    """Run the full pipeline: fetch → script → TTS → video."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*50}")
    print(f"  BTC News Pipeline — {timestamp}")
    print(f"{'='*50}\n")

    # Step 1: Fetch news
    print("[1/5] Fetching Bitcoin news...")
    news_data = fetch_all()
    print(f"  → {len(news_data['articles'])} articles found")
    print(f"  → BTC: ${news_data['price']['price_usd']:,.0f} ({news_data['price']['change_24h']:+.2f}%)")

    # Step 2: Generate script
    print("\n[2/5] Generating narration script...")
    script = generate_script(news_data)
    word_count = len(script.split())
    print(f"  → {word_count} words")
    print(f"  → Preview: {script[:100]}...")

    # Step 3: Generate metadata
    print("\n[3/5] Generating title & description...")
    metadata = generate_title_and_description(script)
    print(f"  → Title: {metadata['title']}")

    if dry_run:
        print("\n[DRY RUN] Skipping TTS and video generation.")
        return {"script": script, "metadata": metadata, "news_data": news_data}

    # Step 4: Generate TTS audio
    print("\n[4/5] Generating TTS audio...")
    audio_filename = f"btc_{timestamp}.mp3"
    audio_path = generate_audio(script, audio_filename)

    # Step 5: Compose video
    print("\n[5/5] Composing video...")
    video_filename = f"btc_{timestamp}.mp4"
    video_path = compose_video(audio_path, script, video_filename)

    # Save run log
    log = {
        "timestamp": timestamp,
        "script": script,
        "word_count": word_count,
        "metadata": metadata,
        "audio_path": str(audio_path),
        "video_path": str(video_path),
        "price": news_data["price"],
        "articles_count": len(news_data["articles"]),
    }

    log_dir = OUTPUT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{timestamp}.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n{'='*50}")
    print(f"  ✓ Pipeline complete!")
    print(f"  Video: {video_path}")
    print(f"  Title: {metadata['title']}")
    print(f"  Log:   {log_path}")
    print(f"{'='*50}\n")

    return log


def main():
    parser = argparse.ArgumentParser(description="BTC News YouTube Shorts Pipeline")
    parser.add_argument("--dry", action="store_true", help="Dry run (no TTS/video)")
    args = parser.parse_args()

    run_pipeline(dry_run=args.dry)


if __name__ == "__main__":
    main()
