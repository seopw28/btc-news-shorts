"""Convert API_USAGE_SCRIPT.md to a professional PDF."""
import re
import markdown
from fpdf import FPDF
from pathlib import Path


class APIPdf(FPDF):
    DARK = (30, 30, 30)
    GRAY = (80, 80, 80)
    LIGHT_GRAY = (120, 120, 120)
    ACCENT = (0, 102, 204)
    TABLE_HEADER_BG = (41, 65, 94)
    TABLE_ROW_BG = (245, 247, 250)
    WHITE = (255, 255, 255)
    BORDER_COLOR = (200, 210, 220)

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        # Register fonts
        font_dir = Path(r"C:\Windows\Fonts")
        self.add_font("Pretendard", "", str(font_dir / "malgun.ttf"))
        self.add_font("Pretendard", "B", str(font_dir / "malgunbd.ttf"))
        self.add_font("Mono", "", str(font_dir / "consola.ttf"))

    def header(self):
        if self.page_no() > 1:
            self.set_font("Pretendard", "", 8)
            self.set_text_color(*self.LIGHT_GRAY)
            self.cell(0, 8, "YouTube Data API v3 — Usage Script & End Results", align="R")
            self.ln(4)
            self.set_draw_color(*self.BORDER_COLOR)
            self.line(15, self.get_y(), self.w - 15, self.get_y())
            self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Pretendard", "", 8)
        self.set_text_color(*self.LIGHT_GRAY)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font("Pretendard", "B", 28)
        self.set_text_color(*self.DARK)
        self.cell(0, 14, "YouTube Data API v3", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Pretendard", "", 18)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 12, "Usage Script & End Results", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(20)

        # Info box
        self.set_fill_color(*self.TABLE_ROW_BG)
        self.set_draw_color(*self.BORDER_COLOR)
        x0 = 40
        w0 = self.w - 80
        self.set_xy(x0, self.get_y())
        self.rect(x0, self.get_y(), w0, 52, style="DF")

        self.set_xy(x0 + 8, self.get_y() + 6)
        info_lines = [
            ("Project", "BTC News Shorts & AI Music Publishing"),
            ("GCP Project", "btc-news-shorts"),
            ("Date", "2026-03-19"),
            ("Channels", "4 YouTube channels (3 News + 1 Music)"),
        ]
        self.set_font("Pretendard", "", 11)
        for label, value in info_lines:
            self.set_text_color(*self.LIGHT_GRAY)
            self.cell(32, 10, label, new_x="END")
            self.set_text_color(*self.DARK)
            self.cell(0, 10, value, new_x="LMARGIN", new_y="NEXT")
            self.set_x(x0 + 8)

    def section_heading(self, number, title):
        self.ln(6)
        self.set_font("Pretendard", "B", 16)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 10, f"{number}. {title}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*self.ACCENT)
        self.line(15, self.get_y(), 80, self.get_y())
        self.ln(5)

    def sub_heading(self, title):
        self.ln(3)
        self.set_font("Pretendard", "B", 12)
        self.set_text_color(*self.DARK)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font("Pretendard", "", 10)
        self.set_text_color(*self.GRAY)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def bullet(self, text, indent=15):
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font("Pretendard", "", 10)
        self.set_text_color(*self.GRAY)
        self.cell(5, 6, "\u2022")
        self.multi_cell(0, 6, text)
        self.set_x(x)

    def bold_text(self, label, value):
        self.set_font("Pretendard", "B", 10)
        self.set_text_color(*self.DARK)
        self.cell(self.get_string_width(label) + 2, 6, label, new_x="END")
        self.set_font("Pretendard", "", 10)
        self.set_text_color(*self.GRAY)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def add_table(self, headers, rows, col_widths=None):
        if col_widths is None:
            total = self.w - 30
            col_widths = [total / len(headers)] * len(headers)

        # Check if table fits on current page
        needed = 8 + len(rows) * 7 + 4
        if self.get_y() + needed > self.h - 25:
            self.add_page()

        self.set_font("Pretendard", "B", 9)
        self.set_fill_color(*self.TABLE_HEADER_BG)
        self.set_text_color(*self.WHITE)
        self.set_draw_color(*self.BORDER_COLOR)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border=1, fill=True, align="C")
        self.ln()

        self.set_font("Pretendard", "", 9)
        for ri, row in enumerate(rows):
            if ri % 2 == 0:
                self.set_fill_color(*self.TABLE_ROW_BG)
            else:
                self.set_fill_color(*self.WHITE)
            self.set_text_color(*self.DARK)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 7, str(cell), border=1, fill=True, align="C")
            self.ln()
        self.ln(4)

    def code_block(self, code, lang=""):
        self.set_fill_color(40, 44, 52)
        self.set_text_color(171, 178, 191)
        self.set_font("Mono", "", 7.5)

        lines = code.strip().split("\n")
        line_h = 4.2
        block_h = len(lines) * line_h + 10

        # Page break if needed
        if self.get_y() + block_h > self.h - 25:
            self.add_page()

        x0 = 15
        y0 = self.get_y()
        w0 = self.w - 30

        # Draw background
        self.rect(x0, y0, w0, block_h, style="F")

        # Language label
        if lang:
            self.set_xy(x0 + w0 - 25, y0 + 1)
            self.set_text_color(100, 110, 120)
            self.set_font("Mono", "", 6)
            self.cell(22, 4, lang, align="R")

        self.set_font("Mono", "", 7.5)
        self.set_text_color(171, 178, 191)
        self.set_xy(x0 + 6, y0 + 5)
        for line in lines:
            # Truncate long lines
            if len(line) > 95:
                line = line[:92] + "..."
            self.cell(0, line_h, line, new_x="LMARGIN", new_y="NEXT")
            self.set_x(x0 + 6)

        self.set_y(y0 + block_h + 3)


def build_pdf():
    pdf = APIPdf()
    pdf.alias_nb_pages()

    # === Title Page ===
    pdf.add_title_page()

    # === Section 1: Overview ===
    pdf.add_page()
    pdf.section_heading("1", "Project Overview")
    pdf.body_text(
        "We operate two automated pipelines under one GCP project, "
        "serving a total of 4 YouTube channels:"
    )

    pdf.sub_heading("Pipeline A \u2014 BTC News Shorts")
    pdf.bullet("Fetches the latest Bitcoin/crypto news from public APIs")
    pdf.bullet("Generates narration scripts and TTS audio")
    pdf.bullet("Composes vertical short-form videos (1080\u00d71920, <60s)")
    pdf.bullet("Uploads to YouTube via Data API v3 across 3 language channels (EN, KO, JA)")
    pdf.bullet("Attaches SRT caption files for accessibility and SEO")
    pdf.bullet("Publishes 1\u20132 videos per channel per day")
    pdf.ln(3)

    pdf.sub_heading("Pipeline B \u2014 AI Music Publishing")
    pdf.bullet("Generates original music tracks via AI composition")
    pdf.bullet("Combines audio with cover art into video format (MP4)")
    pdf.bullet("Uploads to YouTube via Data API v3 (1 music channel)")
    pdf.bullet("Publishes 1\u20133 tracks per day")

    # === Section 2: API Endpoints ===
    pdf.section_heading("2", "YouTube API Endpoints Used")
    pdf.add_table(
        ["Endpoint", "Purpose", "Quota Cost", "Used By"],
        [
            ["videos.insert", "Upload MP4 video", "1,600 units", "Both"],
            ["captions.insert", "Attach SRT subtitle", "400 units", "News only"],
        ],
        col_widths=[42, 45, 30, 28],
    )

    pdf.sub_heading("Quota Breakdown Per Run")
    pdf.add_table(
        ["Pipeline", "Per Upload", "Uploads/Run", "Cost/Run"],
        [
            ["News (3 langs)", "2,000 units", "3", "6,000 units"],
            ["Music", "1,600 units", "1\u20133", "1,600\u20134,800 units"],
            ["Combined daily", "\u2014", "\u2014", "7,600\u201316,800 units"],
        ],
        col_widths=[38, 38, 32, 37],
    )

    # === Section 3: Auth ===
    pdf.section_heading("3", "Authentication Flow")
    pdf.bullet("OAuth 2.0 with offline refresh tokens")
    pdf.bullet("Scopes: youtube.upload, youtube.force-ssl")
    pdf.bullet("Separate token files per channel:")
    pdf.bullet("youtube_token_en.json (News EN)", indent=25)
    pdf.bullet("youtube_token_ko.json (News KO)", indent=25)
    pdf.bullet("youtube_token_ja.json (News JA)", indent=25)
    pdf.bullet("youtube_token.json (Music)", indent=25)
    pdf.bullet("First-time auth via browser-based InstalledAppFlow, then cached & auto-refreshed")

    # === Section 4: Source Code ===
    pdf.add_page()
    pdf.section_heading("4", "Upload Source Code")

    pdf.sub_heading("4-A. News Pipeline \u2014 youtube_uploader.py")
    pdf.code_block('''def upload_video(video_path, title, description, tags, privacy, token_filename):
    """Upload a video to YouTube and return the video ID."""
    youtube = get_authenticated_service(token_filename)

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
        str(video_path), mimetype="video/mp4",
        resumable=True, chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    return response["id"]''', lang="python")

    pdf.code_block('''def upload_captions(video_id, srt_path, language, token_filename):
    """Upload an SRT caption track to a YouTube video."""
    youtube = get_authenticated_service(token_filename)

    body = {
        "snippet": {
            "videoId": video_id, "language": language,
            "name": "", "isDraft": False,
        },
    }

    media = MediaFileUpload(str(srt_path), mimetype="application/x-subrip")
    youtube.captions().insert(
        part="snippet", body=body, media_body=media,
    ).execute()''', lang="python")

    pdf.sub_heading("4-B. Music Pipeline \u2014 youtube_uploader.py")
    pdf.code_block('''def upload_audio_as_video(audio_path, cover_path, title, description, tags):
    """Combine audio + cover image into MP4 via FFmpeg, then upload."""
    video_path = _create_video_from_audio(audio_path, cover_path)
    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title, "description": description,
            "tags": tags, "categoryId": "10",  # Music
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4",
        resumable=True, chunksize=1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
    return response["id"]''', lang="python")

    # === Section 5: CLI ===
    pdf.section_heading("5", "Pipeline Execution Scripts (CLI)")
    pdf.code_block('''# News: Generate videos for all 3 languages and upload
python -m src.pipeline --all-langs --upload

# Music: Generate and upload a track
python main.py --upload''', lang="bash")

    # === Section 6: Execution Log ===
    pdf.add_page()
    pdf.section_heading("6", "Actual Execution Log (2026-03-19)")
    pdf.body_text("Below is the real terminal output from today's News pipeline run:")

    pdf.code_block('''==================================================
  BTC News Pipeline - 20260319_072039
  Languages: EN, KO, JA
==================================================

[Quota] 6,000/10,000 used today (2026-03-18 PT)
  Remaining: 4,000 units  |  Can upload: 2 more videos

[QUOTA] Can only upload 2/3 languages. Will upload first 2.

[1] Fetching Bitcoin news...
  -> 36 articles found
  -> BTC: $71,108 (-4.56%)  |  Sentiment: bearish

[2] Generating English narration script...  -> 142 words
[3] Generating title & description...
  -> Title: Fed Freezes Rates, BTC Dumps to $71,100

[4] Generating videos for 2 language(s)...

--- [EN] English ---
  [OK] Audio: btc_20260319_072039_en.mp3 (245.1 KB)
  [OK] Video: btc_20260319_072039_en.mp4 (16.5 MB, 62.7s)
  Uploading to YouTube (English)...
    -> 6% ... 96% uploaded
  [OK] Upload complete: https://youtube.com/shorts/H0eosxyQ56w
  [OK] Caption uploaded: en -> btc_20260319_072039_en.srt

--- [KO] Korean ---
  [OK] Audio: btc_20260319_072039_ko.mp3 (228.8 KB)
  [OK] Video: btc_20260319_072039_ko.mp4 (16.6 MB, 58.6s)
  Uploading to YouTube (Korean)...
    -> 6% ... 96% uploaded
  [OK] Upload complete: https://youtube.com/shorts/hTdSES36tk8
  [OK] Caption uploaded: ko -> btc_20260319_072039_ko.srt

--- [JA] Japanese ---
  [SKIPPED] Insufficient daily quota

==================================================
  Pipeline complete!
  [EN] -> https://youtube.com/shorts/H0eosxyQ56w
  [KO] -> https://youtube.com/shorts/hTdSES36tk8
  [JA] -> Skipped (quota exceeded)
==================================================''', lang="terminal")

    # === Section 7: End Results ===
    pdf.section_heading("7", "End Results")

    pdf.sub_heading("Uploaded Videos (News \u2014 2026-03-19)")
    pdf.add_table(
        ["Language", "Title", "YouTube URL"],
        [
            ["English", "Fed Freezes Rates, BTC Dumps to $71,100", "youtube.com/shorts/H0eosxyQ56w"],
            ["Korean", "\uc5f0\uc900 \uae08\ub9ac \ub3d9\uacb0, BTC $71,100\ub85c \uae09\ub77d", "youtube.com/shorts/hTdSES36tk8"],
            ["Japanese", "(skipped \u2014 quota exceeded)", "\u2014"],
        ],
        col_widths=[25, 65, 55],
    )

    pdf.sub_heading("Video Specifications")
    pdf.add_table(
        ["Spec", "News Shorts", "Music"],
        [
            ["Resolution", "1080\u00d71920 (9:16)", "1920\u00d71080"],
            ["Duration", "~60 seconds", "2\u20135 minutes"],
            ["Format", "MP4 (H.264 + AAC)", "MP4 (H.264 + AAC 192k)"],
            ["Category", "News & Politics (25)", "Music (10)"],
            ["Captions", "SRT per language", "N/A"],
        ],
        col_widths=[35, 55, 55],
    )

    # === Section 8: Quota Increase ===
    pdf.add_page()
    pdf.section_heading("8", "Why We Need a Quota Increase")

    pdf.sub_heading("Current Situation")
    pdf.add_table(
        ["Pipeline", "Daily Quota Need", "Channels"],
        [
            ["News (3 langs \u00d7 1\u20132 runs)", "6,000\u201312,000 units", "3"],
            ["Music (1\u20133 tracks)", "1,600\u20134,800 units", "1"],
            ["Combined daily total", "7,600\u201316,800 units", "4"],
            ["Current daily limit", "10,000 units", "\u2014"],
        ],
        col_widths=[52, 48, 28],
    )

    pdf.sub_heading("The Problem")
    pdf.body_text(
        "The default 10,000-unit quota is insufficient for both pipelines operating "
        "under the same GCP project. As demonstrated in today's execution log:"
    )
    pdf.bullet(
        "A single 3-language News run (6,000) + 1 Music upload (1,600) = 7,600 units"
    )
    pdf.bullet(
        "This leaves only 2,400 units \u2014 not enough for a second News run or more Music tracks"
    )
    pdf.bullet(
        "The Japanese channel is frequently skipped due to quota exhaustion, "
        "directly impacting our Japanese-speaking audience"
    )

    pdf.ln(4)
    pdf.sub_heading("Requested Quota")
    pdf.add_table(
        ["Metric", "Current", "Requested"],
        [
            ["Daily quota", "10,000 units", "60,000 units"],
        ],
        col_widths=[48, 48, 48],
    )

    pdf.body_text("60,000 units/day would allow us to:")
    pdf.bullet("Reliably publish to all 4 channels daily without skipping any language")
    pdf.bullet("Run the News pipeline 2\u00d7 per day for breaking news coverage (12,000 units)")
    pdf.bullet("Upload 3\u20135 Music tracks per day (4,800\u20138,000 units)")
    pdf.bullet("Handle retry scenarios when uploads fail due to network issues")
    pdf.bullet("Accommodate planned growth: additional language channels and increased frequency")

    # === Section 9: Channels ===
    pdf.section_heading("9", "Channel Links")
    pdf.add_table(
        ["Channel", "Type", "URL"],
        [
            ["BTC News (EN)", "News & Politics", "youtube.com/@bit_news_en"],
            ["BTC News (KO)", "News & Politics", "youtube.com/@bit_news_ko"],
            ["BTC News (JA)", "News & Politics", "youtube.com/@bit_news_ja"],
            ["Music", "Music", "youtube.com/@vex_seo"],
        ],
        col_widths=[40, 40, 65],
    )
    pdf.set_font("Pretendard", "", 9)
    pdf.set_text_color(*pdf.LIGHT_GRAY)
    pdf.cell(0, 6, "* Replace with actual channel URLs if different", new_x="LMARGIN", new_y="NEXT")

    # Save
    out_path = Path(__file__).parent / "YouTube_API_Usage_Script.pdf"
    pdf.output(str(out_path))
    print(f"[OK] PDF saved: {out_path}")
    return out_path


if __name__ == "__main__":
    build_pdf()
