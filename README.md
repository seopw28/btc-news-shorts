# BTC News — YouTube Shorts Automation

Automated pipeline for generating daily Bitcoin news YouTube Shorts.

## Pipeline Flow

```
News Fetch (RSS/CoinGecko) → AI Script (GPT-4o) → TTS (ElevenLabs Hope) → Video (FFmpeg) → Upload
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install FFmpeg: https://ffmpeg.org/download.html

3. Copy `.env.example` → `.env` and fill in your API keys.

4. (Optional) Add background videos to `assets/backgrounds/`

## Usage

```bash
# Full pipeline — generates one video
python -m src.pipeline

# Dry run — fetch news + generate script only
python -m src.pipeline --dry
```

## Project Structure

```
├── config/
│   └── settings.py          # All configuration
├── src/
│   ├── news_fetcher.py      # RSS + CoinGecko price data
│   ├── script_generator.py  # AI narration script
│   ├── tts_generator.py     # ElevenLabs TTS
│   ├── video_composer.py    # FFmpeg video assembly
│   └── pipeline.py          # Main orchestrator
├── assets/
│   ├── backgrounds/         # Background videos (mp4)
│   ├── fonts/               # Custom fonts
│   └── music/               # Background music
├── output/
│   ├── audio/               # Generated TTS audio
│   ├── video/               # Intermediate files
│   └── final/               # Final videos ready to upload
├── .env.example
└── requirements.txt
```

## API Keys Required

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| ElevenLabs | TTS (Hope voice) | 10,000 chars/month |
| OpenAI | Script generation | Pay-per-use |
| CoinGecko | BTC price data | Unlimited (basic) |
