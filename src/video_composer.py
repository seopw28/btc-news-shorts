"""
Video composer - combines background, audio, and subtitles into a YouTube Short.
Uses FFmpeg for video processing.
"""

import math
import subprocess
import json
from pathlib import Path
from datetime import datetime
from config.settings import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    OUTPUT_DIR, ASSETS_DIR,
)

CLIP_DURATION = 5  # seconds per background clip


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def generate_subtitles(script: str, audio_duration: float, output_path: Path) -> Path:
    """Generate SRT subtitle file - 3 words per chunk for impact."""
    words = script.split()
    words_per_second = len(words) / audio_duration

    chunk_size = 8
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

    srt_path = output_path.with_suffix(".srt")
    chunk_duration = chunk_size / words_per_second

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, audio_duration)

            start_str = _format_srt_time(start_time)
            end_str = _format_srt_time(end_time)

            f.write(f"{i + 1}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{' '.join(chunk)}\n\n")

    print(f"[OK] Subtitles saved: {srt_path}")
    return srt_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def get_background_clips(duration: float) -> list:
    """Get enough background clips to cover the video duration."""
    from src.background_fetcher import fetch_multiple_backgrounds
    num_clips = math.ceil(duration / CLIP_DURATION)
    return fetch_multiple_backgrounds(count=num_clips)


def compose_video(
    audio_path: Path,
    script: str,
    output_filename: str = None,
    price_data: dict = None,
) -> Path:
    """Compose final video with professional design."""
    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"btc_news_{timestamp}.mp4"

    output_path = OUTPUT_DIR / "final" / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_duration = get_audio_duration(audio_path)

    # Generate subtitles
    srt_path = generate_subtitles(
        script, audio_duration,
        OUTPUT_DIR / "video" / output_filename,
    )

    # Escape SRT path for FFmpeg on Windows
    srt_path_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")

    # Price info for overlay
    price_usd = ""
    change_pct = ""
    change_color = "white"
    change_raw = 0
    if price_data:
        price_usd = f"${price_data.get('price_usd', 0):,.0f}"
        change_raw = price_data.get('change_24h', 0)
        change_pct = f"{change_raw:+.2f}%"
        change_color = "0x00FF88" if change_raw >= 0 else "0xFF4444"

    dur = audio_duration + 0.5

    # Subtitle style - no background (we draw our own full-width bar)
    # Alignment=5 = center-center, MarginV positions within the bar area
    subtitle_filter = (
        f"subtitles='{srt_path_escaped}'"
        f":force_style='FontName=Arial,"
        f"FontSize=7,"
        f"Bold=1,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BackColour=&H00000000,"
        f"BorderStyle=1,"
        f"Outline=1,"
        f"Shadow=0,"
        f"Alignment=10,"
        f"MarginL=10,"
        f"MarginR=10,"
        f"MarginV=80'"
    )

    # Subtitle band position (center of screen)
    sub_band_y = (VIDEO_HEIGHT // 2) - 60
    sub_band_h = 120

    # Build filter graph with multi-clip background (switches every 5 sec)
    bg_clips = get_background_clips(dur)

    if bg_clips:
        # Multiple background clips - each trimmed to CLIP_DURATION, then concatenated
        input_args = []
        for clip in bg_clips:
            input_args.extend(["-i", str(clip)])

        # Audio is the last input
        audio_input_idx = len(bg_clips)

        # Build concat filter: trim each clip, scale, normalize format, then concat
        clip_filters = []
        concat_inputs = ""
        for i in range(len(bg_clips)):
            label = f"c{i}"
            clip_filters.append(
                f"[{i}:v]trim=0:{CLIP_DURATION},setpts=PTS-STARTPTS,"
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                f"format=yuv420p,fps={VIDEO_FPS},"
                f"setsar=1[{label}]"
            )
            concat_inputs += f"[{label}]"

        # Concat all clips into [bg], then start overlay chain
        prefix = ";".join(clip_filters)
        prefix += f";{concat_inputs}concat=n={len(bg_clips)}:v=1:a=0[bg];[bg]format=yuv420p"
        filter_str = prefix
    else:
        # Fallback: gradient background
        input_args = [
            "-f", "lavfi", "-i",
            (
                f"gradients=s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={dur}:r={VIDEO_FPS}"
                f":c0=#0a0e27:c1=#1a0a2e:speed=0.01"
            ),
        ]
        audio_input_idx = 1
        filter_str = "[0:v]null"

    # Darken background for text readability
    filter_str += f",colorbalance=bs=0.05:bm=0.02"

    # ===== TOP HUD =====
    # Frosted glass header bar
    filter_str += (
        f",drawbox=x=0:y=0:w={VIDEO_WIDTH}:h=260:color=0x000000@0.7:t=fill"
    )
    # Top accent line (orange glow)
    filter_str += (
        f",drawbox=x=0:y=0:w={VIDEO_WIDTH}:h=3:color=0xF7931A:t=fill"
    )

    # "BTC" label - left aligned with orange tag
    filter_str += (
        f",drawbox=x=60:y=40:w=100:h=44:color=0xF7931A:t=fill"
    )
    filter_str += (
        f",drawtext=text='BTC':"
        f"fontsize=30:fontcolor=0x000000:"
        f"x=78:y=47"
    )

    # "LIVE" indicator - pulsing dot via drawtext alpha + static label
    filter_str += (
        f",drawtext=text='o':"
        f"fontsize=14:fontcolor=0xFF0000:"
        f"alpha='0.4+0.6*sin(6*t)':"
        f"x=182:y=48"
    )
    filter_str += (
        f",drawtext=text='LIVE':"
        f"fontsize=20:fontcolor=0xFF4444:"
        f"x=200:y=44"
    )

    # Price display - static, clean
    if price_usd:
        filter_str += (
            f",drawtext=text='{price_usd}':"
            f"fontsize=62:fontcolor=white:"
            f"x=60:y=100"
        )

        # Change badge
        badge_color = "0x0A3D1A" if change_raw >= 0 else "0x3D0A0A"
        arrow = "^" if change_raw >= 0 else "v"
        filter_str += (
            f",drawbox=x=60:y=180:w=200:h=40:color={badge_color}:t=fill"
        )
        filter_str += (
            f",drawtext=text='{arrow} {change_pct}':"
            f"fontsize=26:fontcolor={change_color}:"
            f"x=80:y=186"
        )

        # 24h label
        filter_str += (
            f",drawtext=text='24h':"
            f"fontsize=18:fontcolor=0x666666:"
            f"x=270:y=190"
        )

    # Thin separator line
    filter_str += (
        f",drawbox=x=60:y=240:w={VIDEO_WIDTH - 120}:h=1:color=0x333333:t=fill"
    )

    # ===== BOTTOM BAR =====
    filter_str += (
        f",drawbox=x=0:y={VIDEO_HEIGHT - 140}:w={VIDEO_WIDTH}:h=140:color=0x000000@0.7:t=fill"
    )
    # Bottom accent line
    filter_str += (
        f",drawbox=x=0:y={VIDEO_HEIGHT - 3}:w={VIDEO_WIDTH}:h=3:color=0xF7931A:t=fill"
    )
    # Branding
    filter_str += (
        f",drawtext=text='Follow for daily BTC updates':"
        f"fontsize=22:fontcolor=0x888888:"
        f"x=(w-text_w)/2:y={VIDEO_HEIGHT - 90}"
    )

    # ===== SUBTITLE BAND (full-width dark strip across center) =====
    filter_str += (
        f",drawbox=x=0:y={sub_band_y}:w={VIDEO_WIDTH}:h={sub_band_h}"
        f":color=0x000000@0.6:t=fill"
    )
    # Thin accent lines on band edges
    filter_str += (
        f",drawbox=x=0:y={sub_band_y}:w={VIDEO_WIDTH}:h=2"
        f":color=0xF7931A@0.3:t=fill"
    )
    filter_str += (
        f",drawbox=x=0:y={sub_band_y + sub_band_h - 2}:w={VIDEO_WIDTH}:h=2"
        f":color=0xF7931A@0.3:t=fill"
    )
    # Subtitles (rendered on top of the band)
    filter_str += f",{subtitle_filter}"

    filter_str += "[v]"

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-i", str(audio_path),
        "-filter_complex", filter_str,
        "-map", "[v]",
        "-map", f"{audio_input_idx}:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(dur),
        "-r", str(VIDEO_FPS),
        str(output_path),
    ]

    print(f"Composing video...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] FFmpeg failed:\n{result.stderr[-1000:]}")
        raise RuntimeError("Video composition failed")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Video saved: {output_path} ({size_mb:.1f} MB, {audio_duration:.1f}s)")
    return output_path, srt_path


if __name__ == "__main__":
    test_audio = OUTPUT_DIR / "audio" / "test_narration.mp3"
    if test_audio.exists():
        compose_video(
            audio_path=test_audio,
            script="Bitcoin just hit a new all time high.",
            output_filename="test_video.mp4",
            price_data={"price_usd": 71000, "change_24h": 0.3},
        )
    else:
        print(f"Test audio not found at {test_audio}")
