"""
Video composer — combines background, audio, and subtitles into a YouTube Short.
Uses FFmpeg for video processing.
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime
from config.settings import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    SUBTITLE_FONT_SIZE, SUBTITLE_FONT_COLOR, SUBTITLE_BG_COLOR,
    OUTPUT_DIR, ASSETS_DIR,
)


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def generate_subtitles(script: str, audio_duration: float, output_path: Path) -> Path:
    """Generate SRT subtitle file from script, splitting into timed chunks."""
    words = script.split()
    words_per_second = len(words) / audio_duration

    # Split into chunks of ~6 words each
    chunk_size = 6
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

    print(f"✓ Subtitles saved: {srt_path}")
    return srt_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def find_background_video() -> Path:
    """Find a background video from assets, or generate a solid color fallback."""
    bg_dir = ASSETS_DIR / "backgrounds"
    videos = list(bg_dir.glob("*.mp4")) + list(bg_dir.glob("*.mov"))

    if videos:
        return videos[0]  # Use first available background

    # Fallback: generate a dark gradient background
    return None


def compose_video(
    audio_path: Path,
    script: str,
    output_filename: str = None,
) -> Path:
    """Compose final video: background + audio + subtitles."""
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

    bg_video = find_background_video()

    # Escape special characters in SRT path for FFmpeg on Windows
    srt_path_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")

    subtitle_filter = (
        f"subtitles='{srt_path_escaped}'"
        f":force_style='FontSize={SUBTITLE_FONT_SIZE},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BackColour=&H80000000,"
        f"Outline=2,"
        f"Shadow=1,"
        f"Alignment=10,"
        f"MarginV=200'"
    )

    if bg_video:
        # Use existing background video
        cmd = [
            "ffmpeg", "-y",
            "-i", str(bg_video),
            "-i", str(audio_path),
            "-filter_complex", (
                f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                f"loop=-1:size=1:start=0,"
                f"setpts=N/{VIDEO_FPS}/TB,"
                f"{subtitle_filter}[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(audio_duration + 0.5),
            "-r", str(VIDEO_FPS),
            str(output_path),
        ]
    else:
        # Generate dark background with animated gradient
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", (
                f"color=c=0x1a1a2e:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={audio_duration + 0.5}:r={VIDEO_FPS}"
            ),
            "-i", str(audio_path),
            "-filter_complex", (
                f"[0:v]{subtitle_filter},"
                f"drawtext=text='₿ BITCOIN NEWS':"
                f"fontsize=36:fontcolor=orange:"
                f"x=(w-text_w)/2:y=120[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]

    print(f"Composing video...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] FFmpeg failed:\n{result.stderr[-500:]}")
        raise RuntimeError("Video composition failed")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✓ Video saved: {output_path} ({size_mb:.1f} MB, {audio_duration:.1f}s)")
    return output_path


if __name__ == "__main__":
    # Test requires an audio file at output/audio/test_narration.mp3
    test_audio = OUTPUT_DIR / "audio" / "test_narration.mp3"
    if test_audio.exists():
        compose_video(
            audio_path=test_audio,
            script="Bitcoin just hit a new all time high. The world's largest cryptocurrency surged past one hundred thousand dollars today.",
            output_filename="test_video.mp4",
        )
    else:
        print(f"Test audio not found at {test_audio}")
        print("Run tts_generator.py first to create test audio.")
