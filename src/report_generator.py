"""
PDF report generator - creates a local news report for review after pipeline runs.
Uses reportlab for PDF generation with CJK font support.
"""

from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from xml.sax.saxutils import escape as xml_escape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from config.settings import OUTPUT_DIR
from src.script_generator import _call_llm

# Try to register CJK-capable fonts
_CJK_FONT = "Helvetica"
for font_path in [
    "C:/Windows/Fonts/malgun.ttf",      # Windows Korean
    "C:/Windows/Fonts/meiryo.ttc",       # Windows Japanese
    "C:/Windows/Fonts/msyh.ttc",         # Windows Chinese
    "C:/Windows/Fonts/arial.ttf",        # Fallback
]:
    if Path(font_path).exists():
        try:
            name = Path(font_path).stem
            pdfmetrics.registerFont(TTFont(name, font_path))
            _CJK_FONT = name
            break
        except Exception:
            continue

# 감정 라벨 한글 매핑
SENTIMENT_KO = {
    "surge": "급등",
    "crash": "급락",
    "bullish": "상승세",
    "bearish": "하락세",
    "sideways": "횡보",
}


def _make_styles():
    """Create PDF styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=_CJK_FONT,
        fontSize=20,
        textColor=HexColor("#F7931A"),
        spaceAfter=6 * mm,
    ))
    styles.add(ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontName=_CJK_FONT,
        fontSize=14,
        textColor=HexColor("#1a1a2e"),
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    ))
    styles.add(ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=_CJK_FONT,
        fontSize=10,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        "Script",
        parent=styles["BodyText"],
        fontName=_CJK_FONT,
        fontSize=10,
        leading=14,
        leftIndent=10 * mm,
        rightIndent=10 * mm,
        backColor=HexColor("#f5f5f5"),
        borderPadding=4 * mm,
    ))
    styles.add(ParagraphStyle(
        "Meta",
        parent=styles["BodyText"],
        fontName=_CJK_FONT,
        fontSize=9,
        textColor=HexColor("#666666"),
    ))
    return styles


def _translate_articles_to_korean(articles: list[dict]) -> list[dict]:
    """Translate article titles and summaries to Korean via LLM."""
    if not articles:
        return articles

    # Build batch translation prompt
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. TITLE: {a.get('title', '')}")
        if a.get("summary"):
            lines.append(f"   SUMMARY: {a['summary'][:200]}")

    prompt = (
        "아래 비트코인/크립토 뉴스 기사들의 제목과 요약을 한국어로 번역해줘.\n"
        "규칙:\n"
        "- 각 기사마다 번호를 유지하고 TITLE:, SUMMARY: 형식을 그대로 써줘\n"
        "- 자연스러운 한국어로 번역 (의역 OK)\n"
        "- 출력 형식만 지켜줘, 다른 설명 없이\n\n"
        + "\n".join(lines)
    )

    try:
        result = _call_llm(prompt)
    except Exception as e:
        print(f"  [WARN] 기사 번역 실패, 원문 사용: {e}")
        return articles

    # Parse translated results back
    translated = []
    current_title = ""
    current_summary = ""
    current_idx = 0

    for line in result.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Check for numbered title line
        for idx in range(1, len(articles) + 1):
            prefix = f"{idx}."
            if stripped.startswith(prefix):
                # Save previous
                if current_idx > 0 and current_idx <= len(articles):
                    translated.append({
                        **articles[current_idx - 1],
                        "title_ko": current_title,
                        "summary_ko": current_summary,
                    })
                current_idx = idx
                # Extract title
                rest = stripped[len(prefix):].strip()
                if rest.upper().startswith("TITLE:"):
                    rest = rest[6:].strip()
                current_title = rest
                current_summary = ""
                break
        else:
            # Check for summary line
            if stripped.upper().startswith("SUMMARY:"):
                current_summary = stripped[8:].strip()
            elif current_summary == "" and "TITLE" not in stripped.upper():
                current_summary = stripped

    # Save last one
    if current_idx > 0 and current_idx <= len(articles):
        translated.append({
            **articles[current_idx - 1],
            "title_ko": current_title,
            "summary_ko": current_summary,
        })

    # Fill any missing translations with originals
    while len(translated) < len(articles):
        idx = len(translated)
        translated.append({
            **articles[idx],
            "title_ko": articles[idx].get("title", ""),
            "summary_ko": articles[idx].get("summary", ""),
        })

    return translated


def _translate_script_to_korean(en_script: str) -> str:
    """Translate the English script summary to Korean."""
    prompt = (
        "아래 비트코인 뉴스 대본을 한국어로 자연스럽게 번역해줘.\n"
        "규칙:\n"
        "- 숫자/가격은 그대로 유지 ($71,452, +0.81% 등)\n"
        "- 자연스러운 한국어, 뉴스 앵커 톤\n"
        "- 출력만, 다른 설명 없이\n\n"
        f"{en_script}"
    )
    try:
        return _call_llm(prompt)
    except Exception:
        return en_script


def generate_report(
    news_data: dict,
    en_script: str,
    en_metadata: dict,
    lang_results: list[dict] = None,
    report_type: str = "news",
    topic: str = None,
) -> Path:
    """Generate a PDF report summarizing the pipeline run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = OUTPUT_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = report_dir / f"{report_type}_{timestamp}.pdf"

    styles = _make_styles()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    story = []

    # 제목
    if report_type == "education":
        story.append(Paragraph("BTC 교육 콘텐츠 리포트", styles["ReportTitle"]))
    else:
        story.append(Paragraph("BTC 뉴스 리포트", styles["ReportTitle"]))

    story.append(Paragraph(
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["Meta"],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", color=HexColor("#F7931A"), thickness=2))

    # 시세 정보
    if news_data and news_data.get("price"):
        price = news_data["price"]
        story.append(Spacer(1, 4 * mm))

        sentiment = news_data.get("sentiment", "sideways")
        sentiment_ko = SENTIMENT_KO.get(sentiment, sentiment)
        story.append(Paragraph(f"시세 현황 ({sentiment_ko})", styles["SectionHead"]))

        change = price.get("change_24h", 0)
        change_color = "#00AA55" if change >= 0 else "#DD3333"
        price_table = Table(
            [
                ["BTC 가격", f"${price.get('price_usd', 0):,.0f}"],
                ["24시간 변동", f"{change:+.2f}%"],
                ["시가총액", f"${price.get('market_cap', 0):,.0f}"],
            ],
            colWidths=[50 * mm, 80 * mm],
        )
        price_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("FONTSIZE", (1, 0), (1, 0), 16),
            ("TEXTCOLOR", (1, 1), (1, 1), HexColor(change_color)),
            ("FONTNAME", (0, 0), (0, -1), _CJK_FONT),
            ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#666666")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(price_table)

    # 주요 헤드라인 (한글 번역)
    if news_data and news_data.get("articles"):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("주요 헤드라인", styles["SectionHead"]))

        articles = news_data["articles"][:5]
        print("  리포트용 기사 한글 번역 중...")
        translated = _translate_articles_to_korean(articles)

        for i, article in enumerate(translated, 1):
            source = xml_escape(article.get("source", "Unknown"))
            # 한글 제목 우선, 없으면 원문
            title_ko = xml_escape(article.get("title_ko", article.get("title", "")))
            summary_ko = xml_escape(article.get("summary_ko", article.get("summary", ""))[:150])
            title_en = xml_escape(article.get("title", ""))

            story.append(Paragraph(
                f"<b>{i}. [{source}]</b> {title_ko}",
                styles["Body"],
            ))
            if summary_ko:
                story.append(Paragraph(
                    f"<i>{summary_ko}</i>",
                    styles["Meta"],
                ))
            # 원문 제목도 작게 표시
            story.append(Paragraph(
                f"<i>원문: {title_en}</i>",
                styles["Meta"],
            ))
            story.append(Spacer(1, 2 * mm))

    # 교육 주제
    if topic:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("교육 주제", styles["SectionHead"]))
        story.append(Paragraph(topic, styles["Body"]))

    # 대본 (한글 번역)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("대본 내용", styles["SectionHead"]))
    story.append(Paragraph(
        f"단어 수: {len(en_script.split())} | "
        f"제목: {xml_escape(en_metadata.get('title', 'N/A'))}",
        styles["Meta"],
    ))
    story.append(Spacer(1, 2 * mm))

    print("  리포트용 대본 한글 번역 중...")
    ko_script = _translate_script_to_korean(en_script)
    script_html = xml_escape(ko_script).replace("\n", "<br/>")
    story.append(Paragraph(script_html, styles["Script"]))

    # 원문 대본 (접어서 표시)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("원문 (English)", styles["Meta"]))
    en_script_html = xml_escape(en_script).replace("\n", "<br/>")
    story.append(Paragraph(en_script_html, styles["Script"]))

    # 언어별 결과
    lang_labels = {"en": "영어", "ko": "한국어", "ja": "일본어"}
    if lang_results:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("언어별 생성 결과", styles["SectionHead"]))
        story.append(HRFlowable(width="100%", color=HexColor("#dddddd"), thickness=1))

        for result in lang_results:
            if result.get("skipped"):
                lang_code = result.get("lang", "??")
                lang_label = lang_labels.get(lang_code, lang_code.upper())
                reason = result.get("reason", "알 수 없음")
                story.append(Spacer(1, 3 * mm))
                story.append(Paragraph(
                    f"{lang_label} — 건너뜀 ({reason})",
                    styles["Meta"],
                ))
                continue

            lang_code = result.get("lang", "??")
            lang_label = lang_labels.get(lang_code, lang_code.upper())
            script = result.get("display_script", result.get("script", ""))
            metadata = result.get("metadata", {})

            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph(f"{lang_label} 버전", styles["SectionHead"]))
            story.append(Paragraph(
                f"제목: {xml_escape(metadata.get('title', 'N/A'))} | "
                f"글자 수: {len(script)}자",
                styles["Meta"],
            ))
            story.append(Spacer(1, 2 * mm))
            script_html = xml_escape(script).replace("\n", "<br/>")
            story.append(Paragraph(script_html, styles["Script"]))

            if result.get("video_path"):
                story.append(Paragraph(
                    f"영상: {result['video_path']}",
                    styles["Meta"],
                ))
            if result.get("video_id"):
                story.append(Paragraph(
                    f"YouTube: https://youtube.com/shorts/{result['video_id']}",
                    styles["Meta"],
                ))

    # Build PDF
    doc.build(story)
    print(f"[OK] PDF 리포트 저장: {pdf_path}")
    return pdf_path
