"""
Video composer - combines background, audio, and subtitles into a YouTube Short.
Uses FFmpeg for video processing.
"""

import math
import subprocess
import json
import glob as glob_mod
import random
from pathlib import Path
from datetime import datetime
from config.settings import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    OUTPUT_DIR, ASSETS_DIR,
)

CLIP_DURATION = 3  # seconds per background clip (fast cuts for Shorts)
XFADE_DURATION = 0.1  # quick fadeblack transition between clips
HOOK_DURATION = 0.8  # total hook duration (0-0.3s punch-in, 0.3-0.8s context)


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of audio file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_path)],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _split_sentences(script: str) -> list[str]:
    """Split script into sentences, respecting punctuation boundaries.
    Avoids splitting on decimal points (e.g. 1.16%) or abbreviations.
    """
    import re
    # Detect CJK-heavy text
    cjk_count = sum(1 for c in script if '\u3000' <= c <= '\u9fff' or '\uac00' <= c <= '\ud7af')
    is_cjk = cjk_count > len(script) * 0.3

    if is_cjk:
        # Split on CJK sentence-ending punctuation, but NOT on decimal points (digit.digit)
        # Also not on $ amounts like $71,512.50
        parts = re.split(r'(?<=[。！？])\s*|(?<=[^\d][\.\!\?])(?!\d)\s*', script.strip())
    else:
        # Split on sentence-ending punctuation followed by space, but NOT decimal points
        parts = re.split(r'(?<=[^\d][.!?])(?!\d)\s+', script.strip())

    return [p.strip() for p in parts if p.strip()]


def _chunk_text(script: str, max_chars: int = None) -> tuple[list[str], list[int]]:
    """Split script into subtitle chunks at sentence boundaries.
    Each chunk is max 2 lines, each line up to max_chars.
    Returns (chunks, sentence_ids) where sentence_ids[i] = source sentence index.
    """
    sentences = _split_sentences(script)

    # Detect script type: Japanese/Chinese (no spaces) vs Korean/Latin (spaces)
    cjk_count = sum(1 for c in script if '\u3000' <= c <= '\u9fff')
    ko_count = sum(1 for c in script if '\uac00' <= c <= '\ud7af')
    is_ja_zh = cjk_count > len(script) * 0.3  # Japanese/Chinese (character-based)
    is_ko = ko_count > len(script) * 0.3       # Korean (word-based, uses spaces)

    if max_chars is None:
        max_chars = 22 if is_ja_zh else 20  # JA/ZH wider chars need fewer per line
    max_chunk_chars = max_chars * 2 + 1

    chunks = []
    chunk_sent_ids = []
    for sent_idx, sentence in enumerate(sentences):
        if is_ja_zh:
            # Japanese/Chinese: character-based splitting (no spaces between words)
            import re as _re
            lines = []
            remaining = sentence
            while len(remaining) > max_chars:
                cut = -1
                search_start = max_chars // 2
                search_end = max_chars + 5
                for p in ["、", "，", " "]:
                    idx = remaining.find(p, search_start, search_end)
                    if idx != -1:
                        cut = idx + 1
                        break
                # Try comma only if not between digits
                if cut == -1:
                    for m in _re.finditer(r",", remaining[search_start:search_end]):
                        pos = search_start + m.start()
                        if pos > 0 and pos < len(remaining) - 1:
                            if remaining[pos - 1].isdigit() and remaining[pos + 1].isdigit():
                                continue
                        cut = pos + 1
                        break
                if cut == -1:
                    cut = max_chars
                lines.append(remaining[:cut].strip())
                remaining = remaining[cut:].strip()
            if remaining:
                lines.append(remaining)
        else:
            # Korean/Latin: word-based splitting (uses spaces between words)
            words = sentence.split()
            lines = []
            current = []
            for word in words:
                test = " ".join(current + [word])
                if len(test) > max_chars and current:
                    lines.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                lines.append(" ".join(current))

        # Group lines into 2-line chunks
        for i in range(0, len(lines), 2):
            chunk = "\n".join(lines[i:i + 2])
            chunks.append(chunk)
            chunk_sent_ids.append(sent_idx)

    # Orphan chunk prevention: merge very short chunks with previous chunk
    if len(chunks) > 1:
        merged = [chunks[0]]
        merged_ids = [chunk_sent_ids[0]]
        for idx, chunk in enumerate(chunks[1:], 1):
            plain = chunk.replace("\n", " ").strip()
            word_ct = len(plain.split())
            char_ct = len(plain)
            is_orphan = False
            if is_ja_zh:
                is_orphan = char_ct <= 4
            elif is_ko:
                is_orphan = word_ct <= 1 or char_ct <= 5
            else:
                is_orphan = word_ct <= 1 or char_ct <= 5

            if is_orphan and merged:
                # Merge with previous chunk
                prev = merged[-1]
                prev_lines = prev.split("\n")
                prev_lines[-1] = prev_lines[-1] + " " + plain
                merged[-1] = "\n".join(prev_lines[:2])
            else:
                merged.append(chunk)
                merged_ids.append(chunk_sent_ids[idx])
        chunks = merged
        chunk_sent_ids = merged_ids

    return chunks, chunk_sent_ids


def _word_count(text: str) -> int:
    """Count words (Latin/Korean) or characters (Japanese/Chinese) for timing."""
    ja_zh_count = sum(1 for c in text if '\u3000' <= c <= '\u9fff')
    if ja_zh_count > len(text.replace(" ", "")) * 0.3:
        # Japanese/Chinese: count characters (no word boundaries)
        return len(text.replace(" ", "").replace("\n", ""))
    # Korean/Latin: count words (space-separated)
    return len(text.split())


def _detect_silence(audio_path: Path, noise_db: int = -30, min_dur: float = 0.07) -> list[float]:
    """Detect silence boundaries in audio using FFmpeg silencedetect.
    Returns list of midpoints of silence intervals (natural break points).
    """
    import re as _re
    result = subprocess.run(
        ["ffmpeg", "-i", str(audio_path),
         "-af", f"silencedetect=n={noise_db}dB:d={min_dur}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(m) for m in _re.findall(r"silence_start:\s*([\d.]+)", result.stderr)]
    ends = [float(m) for m in _re.findall(r"silence_end:\s*([\d.]+)", result.stderr)]
    # Return midpoint of each silence interval as the break point
    breaks = []
    for s, e in zip(starts, ends):
        breaks.append((s + e) / 2)
    return breaks


def _align_chunks_to_silence(
    chunks: list[str], audio_duration: float, silence_breaks: list[float],
) -> list[tuple[float, float]]:
    """Align subtitle chunks to detected silence boundaries.
    Uses word-count proportional timing as base, then snaps boundaries to
    nearest silence break points for natural alignment.
    """
    num_chunks = len(chunks)
    if num_chunks <= 1:
        return [(0.0, audio_duration)]

    # Step 1: word-count proportional boundaries as initial estimate
    word_counts = [_word_count(c) for c in chunks]
    total_words = sum(word_counts) or 1
    boundaries = []
    t = 0.0
    for wc in word_counts[:-1]:
        t += (wc / total_words) * audio_duration
        boundaries.append(t)

    # Step 2: snap each boundary to nearest silence break (within tolerance)
    snap_tolerance = audio_duration * 0.08  # 8% of total duration
    snapped = []
    used_breaks = set()
    for b in boundaries:
        best = b
        best_dist = snap_tolerance
        best_idx = -1
        for j, sb in enumerate(silence_breaks):
            dist = abs(sb - b)
            if dist < best_dist and j not in used_breaks:
                best = sb
                best_dist = dist
                best_idx = j
        if best_idx >= 0:
            used_breaks.add(best_idx)
        snapped.append(best)

    # Step 3: enforce monotonicity (each boundary must be after the previous)
    min_gap = 1.0  # minimum 1 second per chunk
    for i in range(1, len(snapped)):
        if snapped[i] <= snapped[i - 1] + min_gap:
            snapped[i] = snapped[i - 1] + min_gap

    # Step 4: build (start, end) pairs
    times = []
    prev = 0.0
    for s in snapped:
        if s >= audio_duration:
            s = audio_duration - 0.1
        times.append((prev, s))
        prev = s
    times.append((prev, audio_duration))

    # Step 5: ensure no chunk is shorter than min_display (steal from previous)
    min_display = 1.0
    for i in range(len(times) - 1, 0, -1):
        start, end = times[i]
        if end - start < min_display:
            new_start = max(0, end - min_display)
            # Don't overlap with chunks before the previous one
            if new_start < times[i - 1][0] + min_display:
                new_start = times[i - 1][0] + min_display
            times[i] = (new_start, end)
            times[i - 1] = (times[i - 1][0], new_start)

    return times


def _distribute_sentence_timing(
    display_chunks: list[str],
    display_sent_ids: list[int],
    sentence_times: list[tuple[float, float]],
    audio_duration: float,
) -> list[tuple[float, float]]:
    """Distribute sentence-level timing to individual display chunks.

    Each sentence's time budget is split proportionally across its chunks
    using word count. This ensures subtitle timing follows speech rhythm
    even when display text (digits) differs from TTS text (spelled-out).
    """
    chunk_times = []

    # Group chunks by sentence
    from collections import defaultdict
    sent_chunks = defaultdict(list)
    for i, sid in enumerate(display_sent_ids):
        sent_chunks[sid].append(i)

    for sid in sorted(sent_chunks.keys()):
        chunk_indices = sent_chunks[sid]

        # Get sentence time range
        if sid < len(sentence_times):
            sent_start, sent_end = sentence_times[sid]
        else:
            # More display sentences than tts sentences — use remaining time
            sent_start = chunk_times[-1][1] if chunk_times else 0.0
            sent_end = audio_duration

        sent_dur = sent_end - sent_start

        # Proportionally distribute within sentence using word count
        word_counts = [_word_count(display_chunks[i]) for i in chunk_indices]
        total_wc = sum(word_counts) or 1

        t = sent_start
        for j, ci in enumerate(chunk_indices):
            if j == len(chunk_indices) - 1:
                # Last chunk in sentence gets remaining time
                chunk_times.append((t, sent_end))
            else:
                sub_dur = (word_counts[j] / total_wc) * sent_dur
                chunk_times.append((t, t + sub_dur))
                t += sub_dur

    # Ensure min display time (1.0s) for all chunks
    min_display = 1.0
    for i in range(len(chunk_times) - 1, 0, -1):
        start, end = chunk_times[i]
        if end - start < min_display:
            new_start = max(0, end - min_display)
            if new_start < chunk_times[i - 1][0] + min_display:
                new_start = chunk_times[i - 1][0] + min_display
            chunk_times[i] = (new_start, end)
            chunk_times[i - 1] = (chunk_times[i - 1][0], new_start)

    return chunk_times


def generate_subtitles(
    script: str, audio_duration: float, output_path: Path,
    audio_path: Path = None,
    tts_script: str = None,
) -> Path:
    """Generate ASS subtitle file with smart chunking for CJK/Latin.
    Also generates SRT for YouTube caption upload.

    If tts_script is provided, uses it for timing calculation (matches audio rhythm)
    while using script (display_script) for subtitle text rendering.
    """
    display_chunks, display_sent_ids = _chunk_text(script)
    num_chunks = len(display_chunks)

    # Calculate timing
    if audio_path and audio_path.exists():
        silence_breaks = _detect_silence(audio_path)

        if tts_script:
            # === SENTENCE-LEVEL TIMING from tts_script (matches audio) ===
            tts_sentences = _split_sentences(tts_script)
            sentence_times = _align_chunks_to_silence(
                tts_sentences, audio_duration, silence_breaks
            )

            # Distribute each sentence's time across its display chunks
            chunk_times = _distribute_sentence_timing(
                display_chunks, display_sent_ids, sentence_times, audio_duration
            )
        else:
            chunk_times = _align_chunks_to_silence(
                display_chunks, audio_duration, silence_breaks
            )
    else:
        word_counts = [_word_count(c) for c in display_chunks]
        total_words = sum(word_counts) or 1
        chunk_durations = [(wc / total_words) * audio_duration for wc in word_counts]
        chunk_times = []
        t = 0.0
        for dur_c in chunk_durations:
            chunk_times.append((t, min(t + dur_c, audio_duration)))
            t += dur_c

    chunks = display_chunks

    # Generate SRT (for YouTube captions)
    srt_path = output_path.with_suffix(".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            start_time, end_time = chunk_times[i]
            f.write(f"{i + 1}\n")
            f.write(f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}\n")
            f.write(f"{chunk}\n\n")

    # Generate ASS (for video burn-in with proper positioning)
    ass_path = output_path.with_suffix(".ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write(f"PlayResX: {VIDEO_WIDTH}\n")
        f.write(f"PlayResY: {VIDEO_HEIGHT}\n")
        f.write("ScaledBorderAndShadow: yes\n")
        f.write("\n[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n")
        # Alignment=5 (middle-center) for precise vertical centering via \pos
        # Modern style: white text, dark outline, soft shadow, slight letter spacing
        f.write(f"Style: Default,Segoe UI,44,&H00FFFFFF,&H00FFFFFF,&H00111111,&H80000000,"
                f"-1,0,0,0,100,100,1.5,0,1,2.5,1.5,5,80,80,0,1\n")
        # Highlight style (cyan accent for keywords)
        f.write(f"Style: Highlight,Segoe UI,46,&H00FFE500,&H00FFFFFF,&H00000000,&H80000000,"
                f"-1,0,0,0,100,100,1.5,0,1,3,1.5,5,80,80,0,1\n")
        f.write("\n[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        sub_cx = VIDEO_WIDTH // 2
        sub_cy = int(VIDEO_HEIGHT * 0.30)
        for i, chunk in enumerate(chunks):
            start_time, end_time = chunk_times[i]
            start_str = _format_ass_time(start_time)
            end_str = _format_ass_time(end_time)
            # Fade-in effect (150ms) + position at subtitle band center
            text = chunk.replace("\n", "\\N")
            f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\fad(150,0)\\pos({sub_cx},{sub_cy})}}{text}\n")

    print(f"[OK] Subtitles saved: {ass_path} ({num_chunks} chunks)")
    return ass_path, srt_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT time format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_ass_time(seconds: float) -> str:
    """Format seconds to ASS time format (H:MM:SS.cc)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def get_background_clips(duration: float) -> list:
    """Get enough background clips to cover the video duration."""
    from src.background_fetcher import fetch_multiple_backgrounds
    num_clips = math.ceil(duration / CLIP_DURATION)
    return fetch_multiple_backgrounds(count=num_clips)


def _find_bgm() -> str | None:
    """Find a BGM file from assets/music/ or output/bgm/. Returns path or None."""
    search_dirs = [ASSETS_DIR / "music", OUTPUT_DIR / "bgm"]
    files = []
    for music_dir in search_dirs:
        if not music_dir.exists():
            continue
        for ext in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
            files.extend(glob_mod.glob(str(music_dir / ext)))
    if not files:
        return None
    return random.choice(files)


def _generate_sparkline_png(sparkline_data: list, output_dir: Path, width: int = 800, height: int = 120) -> Path | None:
    """Generate a 7D sparkline chart as transparent PNG for ffmpeg overlay."""
    if not sparkline_data or len(sparkline_data) < 10:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

        prices = np.array(sparkline_data)
        x = np.arange(len(prices))

        # Line
        ax.plot(x, prices, color="#F7931A", linewidth=2, solid_capstyle="round")
        # Fill under
        ax.fill_between(x, prices.min(), prices, alpha=0.15, color="#F7931A")
        # Current price dot
        ax.plot(x[-1], prices[-1], "o", color="#F7931A", markersize=6)

        ax.set_xlim(0, len(prices) - 1)
        ax.axis("off")
        ax.margins(0, 0.05)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        png_path = output_dir / "sparkline_7d.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png_path, transparent=True, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        return png_path
    except ImportError:
        print("  [WARN] matplotlib not installed, skipping sparkline chart")
        return None


def _generate_vertical_chart_png(sparkline_data: list, output_dir: Path, width: int = 310, height: int = 460) -> Path | None:
    """Generate vertical candlestick chart (7D) for left panel overlay."""
    if not sparkline_data or len(sparkline_data) < 10:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

        prices = np.array(sparkline_data)
        n = len(prices)
        seg = n // 7
        closes = []
        for i in range(7):
            s = i * seg
            e = s + seg if i < 6 else n
            segment = prices[s:e]
            op, cl = segment[0], segment[-1]
            hi, lo = segment.max(), segment.min()
            closes.append(cl)

            is_up = cl >= op
            color = '#22C55E' if is_up else '#FF5555'

            # Wick (high-low range)
            ax.plot([i, i], [lo, hi], color=color, linewidth=2, alpha=0.5, solid_capstyle='round')
            # Body (open-close range)
            body_lo = min(op, cl)
            body_hi = max(op, cl)
            body_h = max(body_hi - body_lo, (hi - lo) * 0.03)
            ax.bar(i, body_h, bottom=body_lo, width=0.55, color=color, alpha=0.85,
                   edgecolor=color, linewidth=0.5)

        # Connecting line through daily closes
        ax.plot(range(7), closes, color='#F7931A', linewidth=1.5, alpha=0.5, zorder=3)
        # Current price dot
        ax.plot(6, closes[-1], 'o', color='#F7931A', markersize=7, zorder=5)

        price_range = prices.max() - prices.min()
        ax.set_ylim(prices.min() - price_range * 0.05, prices.max() + price_range * 0.05)
        ax.set_xlim(-0.6, 6.6)
        ax.axis('off')
        fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)

        png_path = output_dir / "vertical_chart_7d.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png_path, transparent=True, bbox_inches='tight', pad_inches=0.02)
        plt.close(fig)
        return png_path
    except ImportError:
        print("  [WARN] matplotlib not installed, skipping vertical chart")
        return None


def _escape_drawtext(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\u2019")
    text = text.replace(";", "\\;")
    text = text.replace("$", "＄")
    text = text.replace("%", "%%")
    return text


def _generate_prediction_bar_png(
    bullish_pct: float, output_dir: Path,
    width: int = 640, height: int = 140,
) -> Path | None:
    """Generate a BULLISH vs BEARISH prediction bar as transparent PNG.

    Args:
        bullish_pct: Bullish probability (0-100). Bearish = 100 - bullish.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        bearish_pct = 100 - bullish_pct
        is_bullish = bullish_pct >= bearish_pct

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        fig.patch.set_alpha(0)
        ax.set_facecolor("none")

        bar_y = 0.35
        bar_h = 0.30
        gap = 0.008  # gap between bars

        bull_color = "#22C55E" if is_bullish else "#1A7A3A"
        bear_color = "#FF5555" if not is_bullish else "#993333"

        bull_w = (bullish_pct / 100) - gap / 2
        bear_w = (bearish_pct / 100) - gap / 2
        bear_x = bull_w + gap

        # Bullish bar (left)
        bull_rect = mpatches.FancyBboxPatch(
            (0, bar_y), bull_w, bar_h,
            boxstyle="round,pad=0.01", facecolor=bull_color,
            edgecolor="none", alpha=0.95,
        )
        ax.add_patch(bull_rect)

        # Bearish bar (right)
        bear_rect = mpatches.FancyBboxPatch(
            (bear_x, bar_y), bear_w, bar_h,
            boxstyle="round,pad=0.01", facecolor=bear_color,
            edgecolor="none", alpha=0.95,
        )
        ax.add_patch(bear_rect)

        # Winner glow effect (subtle outline on dominant side)
        if is_bullish:
            glow = mpatches.FancyBboxPatch(
                (0, bar_y), bull_w, bar_h,
                boxstyle="round,pad=0.01", facecolor="none",
                edgecolor="#22C55E", linewidth=2, alpha=0.6,
            )
            ax.add_patch(glow)
        else:
            glow = mpatches.FancyBboxPatch(
                (bear_x, bar_y), bear_w, bar_h,
                boxstyle="round,pad=0.01", facecolor="none",
                edgecolor="#FF5555", linewidth=2, alpha=0.6,
            )
            ax.add_patch(glow)

        # Labels
        label_size = 13
        pct_size = 18
        # "BULLISH" label + percentage
        bull_label_weight = "bold" if is_bullish else "normal"
        ax.text(
            bull_w / 2, 0.88, "BULLISH",
            ha="center", va="center", fontsize=label_size,
            color="white", fontweight=bull_label_weight, alpha=0.9,
        )
        ax.text(
            bull_w / 2, 0.12, f"{bullish_pct:.0f}%",
            ha="center", va="center", fontsize=pct_size,
            color=bull_color, fontweight="bold",
        )
        # "BEARISH" label + percentage
        bear_label_weight = "bold" if not is_bullish else "normal"
        ax.text(
            bear_x + bear_w / 2, 0.88, "BEARISH",
            ha="center", va="center", fontsize=label_size,
            color="white", fontweight=bear_label_weight, alpha=0.9,
        )
        ax.text(
            bear_x + bear_w / 2, 0.12, f"{bearish_pct:.0f}%",
            ha="center", va="center", fontsize=pct_size,
            color=bear_color, fontweight="bold",
        )

        # Winner arrow indicator
        if is_bullish:
            ax.text(bull_w / 2, bar_y + bar_h / 2, "▲",
                    ha="center", va="center", fontsize=20, color="white", alpha=0.9)
        else:
            ax.text(bear_x + bear_w / 2, bar_y + bar_h / 2, "▼",
                    ha="center", va="center", fontsize=20, color="white", alpha=0.9)

        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.05, 1.05)
        ax.axis("off")
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

        png_path = output_dir / "prediction_bar.png"
        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png_path, transparent=True, bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        return png_path
    except ImportError:
        print("  [WARN] matplotlib not installed, skipping prediction bar")
        return None


# Max headline characters per language (beyond this, text gets clipped in video)
HEADLINE_MAX_LEN = {
    "en": 45,
    "ko": 22,
    "ja": 22,
    "es": 40,
}
HEADLINE_MAX_LEN_DEFAULT = 40


def _truncate_headline(headline: str, lang: str = "en") -> str:
    """Truncate headline to fit within video width for the given language.

    For EN: cuts at word boundary and appends '...'
    For KO/JA: cuts at character boundary and appends '...'
    """
    max_len = HEADLINE_MAX_LEN.get(lang, HEADLINE_MAX_LEN_DEFAULT)
    if len(headline) <= max_len:
        return headline

    truncated = headline[:max_len]
    if lang in ("en", "es"):
        # Cut at last space to avoid splitting a word
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            truncated = truncated[:last_space]
    # Remove trailing punctuation that looks awkward before ellipsis
    truncated = truncated.rstrip(" ,:;!?、，：")
    return truncated + "..."


def _split_headline(headline: str, max_line: int = 20) -> list[str]:
    """Split headline into max 2 lines at natural break points."""
    if len(headline) <= max_line:
        return [headline]
    mid = len(headline) // 2
    best = mid
    for off in range(min(10, mid)):
        for pos in [mid + off, mid - off]:
            if 0 < pos < len(headline) and headline[pos] in ' ,、，–—·':
                best = pos + (1 if headline[pos] == ' ' else 0)
                break
        else:
            continue
        break
    return [headline[:best].strip(), headline[best:].strip()]


def compose_video(
    audio_path: Path,
    script: str,
    output_filename: str = None,
    price_data: dict = None,
    tts_script: str = None,
    fear_greed: dict = None,
    gold: dict = None,
    dxy: dict = None,
    headline: str = None,
    ta_prediction: dict = None,
    lang: str = "en",
) -> Path:
    """Compose final video with professional design."""
    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"btc_news_{timestamp}.mp4"

    output_path = OUTPUT_DIR / "_build" / "final" / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_duration = get_audio_duration(audio_path)

    # Generate subtitles (ASS for video, SRT for YouTube captions)
    # Pass audio_path for silence-based timing alignment
    # Pass tts_script for accurate timing (matches audio rhythm)
    ass_path, srt_path = generate_subtitles(
        script, audio_duration,
        OUTPUT_DIR / "_build" / "video" / output_filename,
        audio_path=audio_path,
        tts_script=tts_script,
    )

    # Escape ASS path for FFmpeg on Windows
    ass_path_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    # Price info for overlay
    price_usd = ""
    price_prev = ""
    change_pct = ""
    change_color = "white"
    change_raw = 0
    if price_data:
        current_price = price_data.get('price_usd', 0)
        change_raw = price_data.get('change_24h', 0)
        prev_price = current_price / (1 + change_raw / 100) if change_raw != -100 else current_price
        price_usd = f"${current_price:,.0f}"
        price_prev = f"${prev_price:,.0f}"
        change_pct = f"{change_raw:+.2f}%"
        change_color = "0x00FF88" if change_raw >= 0 else "0xFF4444"

    dur = min(audio_duration + 0.5, 59.0)  # YouTube Shorts max 59 seconds

    # Subtitle band dimensions (position set later at lower 1/3)
    sub_band_h = 220

    # Use ASS file directly (style defined in ASS header)
    subtitle_filter = f"ass='{ass_path_escaped}'"

    # ===== BGM (optional) =====
    bgm_path = _find_bgm()

    # Build filter graph with multi-clip background
    bg_clips = get_background_clips(dur)

    if bg_clips:
        input_args = []
        for clip in bg_clips:
            input_args.extend(["-i", str(clip)])

        # Audio input index (after all video clips)
        audio_input_idx = len(bg_clips)

        if len(bg_clips) == 1:
            # Single clip - just trim and scale
            filter_str = (
                f"[0:v]trim=0:{dur},setpts=PTS-STARTPTS,"
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                f"format=yuv420p,fps={VIDEO_FPS},setsar=1"
            )
        else:
            # Multiple clips - trim each, then chain xfade transitions
            clip_filters = []
            for i in range(len(bg_clips)):
                label = f"c{i}"
                clip_filters.append(
                    f"[{i}:v]trim=0:{CLIP_DURATION},setpts=PTS-STARTPTS,"
                    f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                    f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
                    f"format=yuv420p,fps={VIDEO_FPS},"
                    f"setsar=1[{label}]"
                )

            # Chain xfade transitions: c0 + c1 -> xf0, xf0 + c2 -> xf1, ...
            xfade_filters = []
            prev_label = "c0"
            for i in range(1, len(bg_clips)):
                out_label = f"xf{i-1}"
                # offset = point where transition starts (end of accumulated duration minus overlap)
                offset = i * CLIP_DURATION - i * XFADE_DURATION - XFADE_DURATION
                xfade_filters.append(
                    f"[{prev_label}][c{i}]xfade=transition=fadeblack:duration={XFADE_DURATION}:offset={offset:.2f}[{out_label}]"
                )
                prev_label = out_label

            prefix = ";".join(clip_filters + xfade_filters)
            filter_str = f"{prefix};[{prev_label}]format=yuv420p"
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

    # ===== HOOK (3-stage: 0-0.3s number punch-in, 0.3-0.8s context, then content) =====
    if price_data:
        hook_dir = "UP" if change_raw >= 0 else "DOWN"
        hook_color = "0x00FF88" if change_raw >= 0 else "0xFF4444"
        # Dark overlay for hook
        filter_str += (
            f",drawbox=x=0:y=0:w={VIDEO_WIDTH}:h={VIDEO_HEIGHT}:"
            f"color=0x000000@0.6:t=fill:"
            f"enable='lt(t,{HOOK_DURATION})'"
        )
        # Stage 1 (0-0.3s): Giant number punch-in
        hook_number = f"{abs(change_raw):.1f}"
        filter_str += (
            f",drawtext=text='{hook_number}':"
            f"fontsize=240:fontcolor={hook_color}:"
            f"borderw=5:bordercolor=0x000000:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
            f"alpha='if(lt(t,0.3),min(1,t/0.08),max(0,1-(t-0.3)/0.15))':"
            f"enable='lt(t,0.45)'"
        )
        # Stage 2 (0.3-0.8s): Context text "BTC UP/DOWN"
        filter_str += (
            f",drawtext=text='BTC {hook_dir}':"
            f"fontsize=56:fontcolor=white:"
            f"borderw=3:bordercolor=0x000000:"
            f"x=(w-text_w)/2:y=(h/2)+40:"
            f"alpha='if(lt(t,0.3),0,if(lt(t,0.4),min(1,(t-0.3)/0.1),if(lt(t,{HOOK_DURATION - 0.15}),1,max(0,1-(t-{HOOK_DURATION - 0.15})/0.15))))':"
            f"enable='between(t,0.3,{HOOK_DURATION})'"
        )

    # ===== DESIGN #01: Orange Bold Band + Icon Table (LEFT data panel) =====
    hud_enable = f"enable='gte(t,{HOOK_DURATION})'" if price_data else ""
    hud_suffix = f":{hud_enable}" if hud_enable else ""

    # --- HEADLINE (article title as static hook at top, single bold line) ---
    if headline:
        headline = _truncate_headline(headline, lang=lang)
        hl_y = int(VIDEO_HEIGHT * 0.08)
        hl_h = 100
        hl_text = _escape_drawtext(headline)
        # Dark background band
        filter_str += (
            f",drawbox=x=0:y={hl_y}:w={VIDEO_WIDTH}:h={hl_h}"
            f":color=0x000000@0.65:t=fill{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{hl_text}':"
            f"fontsize=42:fontcolor=0xFFFFFF:"
            f"borderw=3:bordercolor=0x000000:"
            f"x=(w-text_w)/2:y={hl_y + hl_h // 2}-text_h/2{hud_suffix}"
        )

    # --- SUBTITLE at ~30% height (full width, black bg) ---
    sub_y = int(VIDEO_HEIGHT * 0.30) - (sub_band_h // 2)
    # Full-width black background box for subtitle
    filter_str += (
        f",drawbox=x=0:y={sub_y}:w={VIDEO_WIDTH}:h={sub_band_h}"
        f":color=0x000000@0.7:t=fill{hud_suffix}"
    )
    # Subtitles (rendered via ASS on top)
    filter_str += f",{subtitle_filter}"

    # --- FULL-WIDTH DATA PANEL (v5: 2-column layout) ---
    if price_data:
        dp_y = int(VIDEO_HEIGHT * 0.50) - 5   # panel content top
        dp_bg_y = dp_y - 30                  # panel background 30px above content
        dp_w = VIDEO_WIDTH                   # full width
        dp_h = 520                           # panel height (from bg_y)
        # Content area (left ~82%, right reserved for YT buttons)
        content_w = int(VIDEO_WIDTH * 0.82)
        col_w = (content_w - 80) // 2       # each column width
        lpad = 55                           # left padding (shifted right)
        col1_x = lpad                       # left column start
        col2_x = lpad + col_w + 20          # right column start

        direction = "+" if change_raw >= 0 else "-"
        change_text = f"{direction}{abs(change_raw):.2f}\uff05"
        pct_color = "0x22C55E" if change_raw >= 0 else "0xFF5555"

        high_24h = price_data.get("high_24h", 0)
        low_24h = price_data.get("low_24h", 0)
        vol_24h = price_data.get("volume_24h", 0)

        high_str = f"${high_24h:,.0f}" if high_24h else "N/A"
        low_str = f"${low_24h:,.0f}" if low_24h else "N/A"
        if vol_24h >= 1e9:
            vol_str = f"${vol_24h / 1e9:.1f}B"
        elif vol_24h >= 1e6:
            vol_str = f"${vol_24h / 1e6:.0f}M"
        else:
            vol_str = f"${vol_24h:,.0f}" if vol_24h else "N/A"

        # Panel background (full width, dark — starts 20px above content)
        filter_str += (
            f",drawbox=x=0:y={dp_bg_y}:w={dp_w}:h={dp_h}"
            f":color=0x0A0E1B@0.92:t=fill{hud_suffix}"
        )
        # Top border accent
        filter_str += (
            f",drawbox=x=0:y={dp_bg_y}:w={dp_w}:h=2"
            f":color=0xF7931A@0.15:t=fill{hud_suffix}"
        )
        # Left border accent
        filter_str += (
            f",drawbox=x=0:y={dp_bg_y}:w=2:h={dp_h}"
            f":color=0xF7931A@0.20:t=fill{hud_suffix}"
        )
        # === TOP ROW: BTC/USD + Price + 24H ===
        # BTC/USD label
        filter_str += (
            f",drawtext=text='BTC/USD':"
            f"fontsize=30:fontcolor=0xF7931A:"
            f"borderw=1:bordercolor=0xF7931A:"
            f"x={col1_x}:y={dp_y + 12}{hud_suffix}"
        )
        # Price (big)
        filter_str += (
            f",drawtext=text='{price_usd}':"
            f"fontsize=52:fontcolor=0xFFFFFF:"
            f"borderw=2:bordercolor=0xFFFFFF:"
            f"x={col1_x}:y={dp_y + 48}{hud_suffix}"
        )
        # 24H change (next to price)
        filter_str += (
            f",drawtext=text='24H  {change_text}':"
            f"fontsize=28:fontcolor={pct_color}:"
            f"borderw=1:bordercolor={pct_color}:"
            f"x={col1_x + 290}:y={dp_y + 68}{hud_suffix}"
        )

        # F&G (right side, BIG and prominent)
        fg_value = fear_greed.get("value", 50) if fear_greed else 50
        fg_label = fear_greed.get("label", "Neutral") if fear_greed else "Neutral"
        fg_color = "0x22C55E" if fg_value >= 55 else ("0xFF5555" if fg_value <= 40 else "0xFDBA74")
        fg_x = content_w - 30
        filter_str += (
            f",drawtext=text='FEAR \\& GREED':"
            f"fontsize=16:fontcolor=0xFFFFFF@0.40:"
            f"x={fg_x}-text_w:y={dp_y + 14}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{fg_value}':"
            f"fontsize=52:fontcolor={fg_color}:"
            f"borderw=2:bordercolor={fg_color}:"
            f"x={fg_x}-text_w:y={dp_y + 36}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{fg_label}':"
            f"fontsize=20:fontcolor={fg_color}:"
            f"borderw=1:bordercolor={fg_color}:"
            f"x={fg_x}-text_w:y={dp_y + 88}{hud_suffix}"
        )

        # Separator
        filter_str += (
            f",drawbox=x={lpad}:y={dp_y + 118}:w={content_w - 2*lpad}:h=1"
            f":color=0xF7931A@0.10:t=fill{hud_suffix}"
        )

        # === DATA ROWS (bigger fonts, 3-column grid) ===
        sec_y = dp_y + 132

        # Row 1: HIGH | LOW | VOL
        data_col_w = (content_w - 2*lpad) // 3
        for i, (label, value) in enumerate([("HIGH", high_str), ("LOW", low_str), ("VOL", vol_str)]):
            cx = lpad + i * data_col_w
            filter_str += (
                f",drawtext=text='{label}':"
                f"fontsize=18:fontcolor=0xFFFFFF@0.40:"
                f"x={cx}:y={sec_y}{hud_suffix}"
            )
            filter_str += (
                f",drawtext=text='{value}':"
                f"fontsize=28:fontcolor=0xFDBA74:"
                f"borderw=1:bordercolor=0xFDBA74:"
                f"x={cx}:y={sec_y + 24}{hud_suffix}"
            )

        # Row 2: GOLD | DXY
        gold_price = f"${gold['price_usd']:,.0f}" if gold else "N/A"
        gold_change_raw = gold.get("change_24h", 0) if gold else 0
        gold_change = f"{'+' if gold_change_raw >= 0 else ''}{gold_change_raw:.1f}%"
        gold_color = "0x22C55E" if gold_change_raw >= 0 else "0xFF5555"
        dxy_val = f"{dxy['value']}" if dxy else "N/A"
        dxy_change_raw = dxy.get("change_24h", 0) if dxy else 0
        dxy_change = f"{'+' if dxy_change_raw >= 0 else ''}{dxy_change_raw:.1f}%"
        dxy_color = "0x22C55E" if dxy_change_raw >= 0 else "0xFF5555"

        row2_y = sec_y + 68
        # GOLD
        filter_str += (
            f",drawtext=text='GOLD':"
            f"fontsize=18:fontcolor=0xFFFFFF@0.40:"
            f"x={lpad}:y={row2_y}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{gold_price}':"
            f"fontsize=26:fontcolor=0xFDBA74:"
            f"x={lpad}:y={row2_y + 24}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{gold_change}':"
            f"fontsize=20:fontcolor={gold_color}:"
            f"x={lpad + 160}:y={row2_y + 28}{hud_suffix}"
        )
        # DXY
        filter_str += (
            f",drawtext=text='DXY':"
            f"fontsize=18:fontcolor=0xFFFFFF@0.40:"
            f"x={lpad + data_col_w}:y={row2_y}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{dxy_val}':"
            f"fontsize=26:fontcolor=0xFDBA74:"
            f"x={lpad + data_col_w}:y={row2_y + 24}{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='{dxy_change}':"
            f"fontsize=20:fontcolor={dxy_color}:"
            f"x={lpad + data_col_w + 120}:y={row2_y + 28}{hud_suffix}"
        )

        # Separator before sparkline
        spark_sep_y = sec_y + 120
        filter_str += (
            f",drawbox=x={lpad}:y={spark_sep_y}:w={content_w - 2*lpad}:h=1"
            f":color=0xF7931A@0.08:t=fill{hud_suffix}"
        )

        # 7D label (centered above sparkline area)
        filter_str += (
            f",drawtext=text='7D':"
            f"fontsize=14:fontcolor=0xF7931A@0.45:"
            f"x={content_w / 2}-text_w/2:y={spark_sep_y + 8}{hud_suffix}"
        )

    else:
        pass

    # === IMAGE OVERLAYS (sparkline, prediction bar) ===
    # Collect all PNG overlays, then chain them sequentially
    overlays = []  # list of (input_args, width, height, x, y)

    # Sparkline chart (only when price_data panel exists)
    if price_data:
        sparkline_data = price_data.get("sparkline_7d", [])
        sparkline_png = _generate_sparkline_png(
            sparkline_data, OUTPUT_DIR / "_build" / "video"
        ) if sparkline_data else None

        if sparkline_png:
            spark_w = content_w - 2*lpad
            spark_h = 200
            overlays.append({
                "png": sparkline_png, "w": spark_w, "h": spark_h,
                "x": lpad, "y": dp_y + 250, "label": "spark",
            })

    # TA Prediction bar
    pred_png = None
    if ta_prediction:
        bullish_pct = ta_prediction.get("bullish", 50)
        pred_png = _generate_prediction_bar_png(
            bullish_pct, OUTPUT_DIR / "_build" / "video"
        )

    if pred_png:
        pred_bar_w = int(VIDEO_WIDTH * 0.82)
        pred_bar_h = 100
        pred_bar_x = int(VIDEO_WIDTH * 0.09)
        pred_bar_y = VIDEO_HEIGHT - pred_bar_h - 60
        # Dark bg + label drawn before overlay
        filter_str += (
            f",drawbox=x={pred_bar_x - 10}:y={pred_bar_y - 28}"
            f":w={pred_bar_w + 20}:h={pred_bar_h + 38}"
            f":color=0x0A0E1B@0.85:t=fill{hud_suffix}"
        )
        filter_str += (
            f",drawtext=text='PREDICTION':"
            f"fontsize=16:fontcolor=0xFFFFFF@0.50:"
            f"x={pred_bar_x}:y={pred_bar_y - 22}{hud_suffix}"
        )
        overlays.append({
            "png": pred_png, "w": pred_bar_w, "h": pred_bar_h,
            "x": pred_bar_x, "y": pred_bar_y, "label": "pred",
        })

    # Chain all overlays
    if overlays:
        prev_label = "v_base"
        filter_str += f"[{prev_label}]"
        for i, ov in enumerate(overlays):
            inp_idx = len(input_args) // 2
            input_args.extend(["-loop", "1", "-t", str(dur), "-i", str(ov["png"])])
            audio_input_idx += 1
            is_last = (i == len(overlays) - 1)
            out_label = "v" if is_last else f"v_ov{i}"
            filter_str += (
                f";[{inp_idx}:v]scale={ov['w']}:{ov['h']},"
                f"format=rgba[{ov['label']}];"
                f"[{prev_label}][{ov['label']}]overlay="
                f"x={ov['x']}:y={ov['y']}:"
                f"enable='gte(t,{HOOK_DURATION})'[{out_label}]"
            )
            prev_label = out_label
    else:
        filter_str += "[v]"

    # ===== AUDIO MIXING (TTS + optional BGM) =====
    if bgm_path:
        # BGM is another input
        bgm_input_idx = audio_input_idx + 1
        input_args_extra = ["-i", str(audio_path), "-i", bgm_path]
        # Mix: TTS at full volume, BGM at -18dB (volume=0.125)
        filter_str += (
            f";[{audio_input_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[tts]"
            f";[{bgm_input_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"volume=0.125,afade=t=out:st={dur - 2}:d=2[bgm]"
            f";[tts][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        audio_map = "[aout]"
    else:
        input_args_extra = ["-i", str(audio_path)]
        audio_map = f"{audio_input_idx}:a"

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        *input_args_extra,
        "-filter_complex", filter_str,
        "-map", "[v]",
        "-map", audio_map,
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
    test_audio = OUTPUT_DIR / "_build" / "audio" / "test_narration.mp3"
    if test_audio.exists():
        compose_video(
            audio_path=test_audio,
            script="Bitcoin just hit a new all time high.",
            output_filename="test_video.mp4",
            price_data={"price_usd": 71000, "change_24h": 0.3},
        )
    else:
        print(f"Test audio not found at {test_audio}")
