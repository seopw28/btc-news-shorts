"""
Expert Panel Discussion - simulates a group of specialists debating
how to improve YouTube Shorts quality.

Each expert brings a different perspective:
  - Video Editor: visual composition, pacing, transitions
  - Social Media Strategist: engagement, hooks, retention
  - Content Creator: storytelling, scripting, audience psychology
  - UX Designer: readability, layout, accessibility

Usage:
    python -m src.expert_panel                         # General quality review
    python -m src.expert_panel --topic "subtitles"     # Focused discussion
    python -m src.expert_panel --video path/to/video   # Review a specific output
    python -m src.expert_panel --script path/to/script # Review a script
"""

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from config.settings import OUTPUT_DIR


EXPERTS = {
    "video_editor": {
        "name": "지훈 (영상 편집 전문가)",
        "emoji": "🎬",
        "role": (
            "숏폼 콘텐츠 10년 이상 경력의 프로 영상 편집자. "
            "YouTube Shorts, TikTok, Reels 전문. 관심 분야: 영상 구도, "
            "페이싱, 전환 효과, 색 보정, 텍스트 배치, 모션 그래픽. "
            "항상 구체적이고 실행 가능한 FFmpeg 또는 편집 조언을 제시."
        ),
    },
    "strategist": {
        "name": "수연 (소셜미디어 전략가)",
        "emoji": "📊",
        "role": (
            "여러 채널을 구독자 100만 이상으로 성장시킨 소셜미디어 전략가. "
            "관심 분야: 훅 효과 (처음 3초), 시청 유지율, CTA, "
            "썸네일/제목 최적화, 게시 스케줄, 시청자 심리. "
            "데이터와 플랫폼별 알고리즘 인사이트로 조언을 뒷받침."
        ),
    },
    "creator": {
        "name": "민준 (크립토 콘텐츠 크리에이터)",
        "emoji": "✍️",
        "role": (
            "구독자 50만 이상의 크립토/금융 콘텐츠 크리에이터. "
            "관심 분야: 스토리텔링 구조, 대본 페이싱, 나레이션 전달 팁, "
            "정보 밀도 vs. 명확성, 시청자 신뢰 구축. "
            "비트코인 콘텐츠에서 무엇이 효과적인지 잘 알고 있음."
        ),
    },
    "ux_designer": {
        "name": "하은 (UX 디자이너)",
        "emoji": "🎨",
        "role": (
            "모바일 우선 영상 앱 작업 경험이 있는 UX/UI 디자이너. "
            "관심 분야: 모바일 화면에서의 텍스트 가독성, 폰트 선택, 대비율, "
            "정보 위계, 자막 위치, 오버레이 디자인, 접근성. "
            "시청자가 작은 폰 화면에서 콘텐츠를 어떻게 소비하는지 고려."
        ),
    },
}

PANEL_SYSTEM = """당신은 YouTube Shorts 품질 향상을 위한 전문가 패널 토론을 진행하는 사회자입니다.
{num_experts}명의 전문가가 각자의 관점에서 집중 토론을 합니다.

반드시 한국어로 토론하세요.

형식 규칙:
- 각 전문가는 토론에서 2-3번 발언
- 전문가들은 서로의 아이디어를 발전시키거나, 반박하거나, 보완해야 함
- 마지막에 합의(CONSENSUS) 섹션: 영향력 순으로 3-5개의 구체적이고 실행 가능한 개선안
- 각 개선안은 구현할 수 있을 만큼 구체적이어야 함 (막연한 조언 금지)
- 각 발언은 다음 형식을 따름:

[전문가 이름]
발언 내용.

...

## 합의 - 핵심 개선안 (영향력 순위)
1. **제목**: 설명 (제안자, 예상 난이도: 낮음/중간/높음)
2. ...
"""

REVIEW_SYSTEM = """당신은 특정 콘텐츠를 리뷰하는 전문가 패널을 진행하는 사회자입니다.
{num_experts}명의 전문가가 제공된 콘텐츠를 분석하고 개선안을 제시합니다.

반드시 한국어로 토론하세요.

형식 규칙:
- 각 전문가는 자신의 고유한 관점에서 콘텐츠를 분석
- 장점과 단점을 모두 파악
- 콘텐츠의 구체적인 부분을 언급
- 마지막에 합의 섹션: 영향력 순으로 3-5개의 구체적 개선안

[전문가 이름]
분석 내용.

...

## 합의 - 핵심 개선안 (영향력 순위)
1. **제목**: 설명 (제안자, 예상 난이도: 낮음/중간/높음)
2. ...
"""


def _call_claude_cli(prompt: str, system: str = None) -> str:
    """Call Claude via local CLI."""
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    if os.name == "nt" and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
        for bash_path in [
            os.path.join(os.path.dirname(shutil.which("git") or ""), "..", "bin", "bash.exe"),
            r"D:\D_program\Git\bin\bash.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if os.path.isfile(bash_path):
                env["CLAUDE_CODE_GIT_BASH_PATH"] = os.path.abspath(bash_path)
                break
    result = subprocess.run(
        ["claude", "-p", full_prompt],
        capture_output=True, text=True, timeout=180, env=env,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr[:500]}")
    return result.stdout.strip()


def _build_expert_context() -> str:
    """Build the expert roster description."""
    lines = ["패널 구성원:\n"]
    for key, expert in EXPERTS.items():
        lines.append(f"- **{expert['name']}**: {expert['role']}\n")
    return "\n".join(lines)


def _build_pipeline_context() -> str:
    """Build context about the current pipeline for general discussions."""
    return """
현재 파이프라인 개요:
- 플랫폼: YouTube Shorts (세로 1080x1920, 최대 59초)
- 콘텐츠: 일일 비트코인/크립토 뉴스 + 교육 콘텐츠
- 언어: 영어, 한국어, 일본어
- TTS: Google Cloud TTS (Chirp3-HD 음성)
- 영상: FFmpeg 합성:
  - 배경 클립 (스톡 영상, 5초마다 전환)
  - 상단 HUD: BTC 가격, 24시간 변동, LIVE 표시
  - 중앙 자막 밴드: ASS 자막 + 반투명 어두운 오버레이
  - 하단 바: 브랜딩 / CTA
- 자막: ASS 형식, Arial 44pt, 흰색 텍스트 + 어두운 윤곽선, 중앙 배치
- 업로드: YouTube Data API v3 + SRT 캡션

알려진 이슈 / 개선 관심 영역:
- 일본어 영상이 가끔 59초 초과
- 한국어 영상 약 60초로 경계선
- 자막 스타일이 더 매력적일 수 있음
- 배경 클립 전환이 하드컷 (크로스페이드 없음)
- 인트로/아웃트로 애니메이션 없음
- 효과음이나 배경음악 없음
- 가격 HUD가 정적 (애니메이션 없음)
"""


def run_panel(
    topic: str = None,
    video_path: str = None,
    script_text: str = None,
) -> dict:
    """Run an expert panel discussion.

    Args:
        topic: Focus topic for general discussion (e.g., "subtitles", "engagement")
        video_path: Path to a video file to review
        script_text: Script text to review

    Returns:
        dict with discussion text and parsed improvements
    """
    expert_context = _build_expert_context()
    num_experts = len(EXPERTS)

    if script_text or video_path:
        # Review mode - analyzing specific content
        system = REVIEW_SYSTEM.format(num_experts=num_experts)
        system += "\n" + expert_context

        if script_text:
            prompt = f"이 비트코인 YouTube Short 나레이션 대본을 리뷰하세요:\n\n```\n{script_text}\n```"
        else:
            prompt = (
                f"영상 경로: {video_path}\n"
                "영상을 직접 볼 수 없으므로, 이 영상을 생성한 파이프라인을 기반으로 분석하세요:\n"
                + _build_pipeline_context()
            )
    else:
        # General discussion mode
        system = PANEL_SYSTEM.format(num_experts=num_experts)
        system += "\n" + expert_context

        pipeline_ctx = _build_pipeline_context()

        if topic:
            prompt = (
                f"토론 주제: YouTube Shorts 파이프라인에서 '{topic}'을(를) 어떻게 개선할 것인가.\n\n"
                f"{pipeline_ctx}\n\n"
                f"각 전문가는 '{topic}'에 대해 자신의 고유한 관점에서 집중하세요. "
                f"구체적이고 실행 가능하게."
            )
        else:
            prompt = (
                f"토론 주제: 비트코인 YouTube Shorts의 조회수와 참여도를 높이기 위해 "
                f"가장 영향력 있는 개선 사항은 무엇인가?\n\n"
                f"{pipeline_ctx}\n\n"
                f"각 전문가는 자신의 관점에서 핵심 개선안을 제시하세요."
            )

    print(f"전문가 패널 소집 중 ({num_experts}명)...")
    if topic:
        print(f"  주제: {topic}")
    discussion = _call_claude_cli(prompt, system=system)

    # Parse consensus items
    improvements = []
    in_consensus = False
    for line in discussion.split("\n"):
        if "합의" in line or ("CONSENSUS" in line.upper() and "IMPROVEMENT" in line.upper()):
            in_consensus = True
            continue
        if in_consensus and line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
            improvements.append(line.strip())

    # Save result
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    panel_dir = OUTPUT_DIR / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "timestamp": timestamp,
        "topic": topic or "general",
        "discussion": discussion,
        "improvements": improvements,
    }

    # Save full discussion as markdown
    md_path = panel_dir / f"panel_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 전문가 패널 토론\n")
        f.write(f"**날짜**: {timestamp}\n")
        f.write(f"**주제**: {topic or '전체 품질 개선'}\n\n")
        f.write("---\n\n")
        f.write(discussion)

    # Save structured data
    json_path = panel_dir / f"panel_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  전문가 패널 토론 완료")
    print(f"  리포트: {md_path}")
    print(f"{'='*50}\n")
    # Safe print for Windows cp949 console
    try:
        print(discussion)
    except UnicodeEncodeError:
        print(discussion.encode("utf-8", errors="replace").decode("utf-8"))

    return result


def main():
    parser = argparse.ArgumentParser(description="Expert Panel Discussion for Shorts Quality")
    parser.add_argument("--topic", type=str, help="Focus topic (e.g., 'subtitles', 'engagement', 'hooks')")
    parser.add_argument("--video", type=str, help="Path to video file to review")
    parser.add_argument("--script", type=str, help="Path to script file to review")
    args = parser.parse_args()

    script_text = None
    if args.script:
        script_path = Path(args.script)
        if script_path.exists():
            script_text = script_path.read_text(encoding="utf-8")
        else:
            print(f"Script file not found: {args.script}")
            return

    run_panel(
        topic=args.topic,
        video_path=args.video,
        script_text=script_text,
    )


if __name__ == "__main__":
    main()
