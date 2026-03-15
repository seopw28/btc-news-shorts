"""
Bitcoin knowledge article generator - creates Shorts-length markdown scripts.
Each topic is split into multiple parts (~60 seconds each).
Uses Google Gemini API. Saved to knowledge/ directory.

Usage:
    python -m src.knowledge_generator                          # Random topic
    python -m src.knowledge_generator --topic "비트코인 반감기"
    python -m src.knowledge_generator --category basics
    python -m src.knowledge_generator --list                   # List all topics
    python -m src.knowledge_generator --batch 5                # Generate 5 random topics
"""

import argparse
import random
import re
from pathlib import Path

from src.script_generator import _call_gemini
from config.settings import BASE_DIR

KNOWLEDGE_DIR = BASE_DIR / "knowledge"

TOPICS = {
    "basics": [
        ("비트코인이란 무엇인가?", "what-is-bitcoin"),
        ("비트코인 거래는 어떻게 이루어지는가", "how-transactions-work"),
        ("비트코인 지갑 - 핫월렛 vs 콜드월렛", "wallets-hot-vs-cold"),
        ("시드 구문(Seed Phrase)이란 무엇이고 왜 중요한가", "seed-phrase"),
        ("비트코인을 안전하게 구매하는 방법", "how-to-buy-bitcoin"),
        ("비트코인 vs 전통 은행 시스템", "bitcoin-vs-banking"),
        ("비트코인 주소란 무엇인가?", "bitcoin-address"),
        ("비트코인 단위 이해하기 - BTC, sats, mBTC", "bitcoin-units"),
    ],
    "technical": [
        ("블록체인 기술은 어떻게 작동하는가", "blockchain-explained"),
        ("비트코인 채굴과 작업증명(Proof of Work)", "mining-proof-of-work"),
        ("라이트닝 네트워크(Lightning Network)란?", "lightning-network"),
        ("비트코인 스크립팅과 스마트 컨트랙트", "bitcoin-scripting"),
        ("세그윗(SegWit) 설명", "segwit"),
        ("탭루트(Taproot) 업그레이드와 그 의미", "taproot"),
        ("비트코인 노드는 어떻게 거래를 검증하는가", "nodes-validation"),
        ("비트코인의 머클 트리(Merkle Tree)", "merkle-trees"),
        ("UTXO 모델 설명", "utxo-model"),
        ("비트코인 난이도 조정 알고리즘", "difficulty-adjustment"),
        ("이중지불 문제와 비트코인의 해결 방법", "double-spending"),
    ],
    "economics": [
        ("비트코인은 왜 2,100만 개로 제한되는가?", "21-million-supply"),
        ("비트코인 반감기와 가격 영향", "halving-cycles"),
        ("인플레이션 헤지 수단으로서의 비트코인", "inflation-hedge"),
        ("비트코인의 Stock-to-Flow 모델", "stock-to-flow"),
        ("비트코인 vs 금 - 가치 저장 수단 비교", "bitcoin-vs-gold"),
        ("비트코인 ETF는 어떻게 작동하는가", "bitcoin-etfs"),
        ("비트코인과 통화 정책", "monetary-policy"),
        ("게임이론과 비트코인 채택", "game-theory"),
        ("비트코인 에너지 소비 논쟁", "energy-debate"),
    ],
    "history": [
        ("사토시 나카모토는 누구인가?", "satoshi-nakamoto"),
        ("비트코인 백서(Whitepaper) 해설", "whitepaper"),
        ("비트코인 가격 역사의 주요 이정표", "price-history"),
        ("마운트곡스(Mt. Gox) 해킹 사건과 그 영향", "mt-gox"),
        ("비트코인 피자데이 - 최초의 실물 거래", "pizza-day"),
        ("블록사이즈 전쟁(Blocksize Wars)", "blocksize-wars"),
        ("엘살바도르의 비트코인 법정화폐 채택", "el-salvador"),
        ("비트코인 포크 - BTC, BCH, BSV", "bitcoin-forks"),
    ],
    "future": [
        ("비트코인은 글로벌 기축통화가 될 수 있을까?", "global-reserve-currency"),
        ("비트코인과 중앙은행 디지털화폐(CBDC)의 공존", "bitcoin-vs-cbdc"),
        ("비트코인이 바꿀 국제 송금의 미래", "future-of-remittance"),
        ("비트코인 채굴과 재생에너지의 결합", "mining-renewable-energy"),
        ("마지막 비트코인이 채굴된 후 - 2140년 시나리오", "after-last-bitcoin"),
        ("비트코인과 AI 경제의 결합 가능성", "bitcoin-and-ai"),
        ("비트코인 레이어2 생태계의 미래", "layer2-ecosystem"),
        ("기관 투자자와 비트코인 - 월스트리트의 변화", "institutional-adoption"),
        ("비트코인이 만드는 개인 금융 주권의 시대", "financial-sovereignty"),
        ("하이퍼비트코이나이제이션 - 비트코인 표준 경제란?", "hyperbitcoinization"),
    ],
}

ARTICLE_PROMPT = """You are a Bitcoin educator writing YouTube Shorts narration scripts in Korean.

Given a topic, break it down into multiple SHORT parts. Each part = 1 YouTube Shorts video (~60 seconds).

Rules:
- Write entirely in Korean (한국어)
- Technical terms: 한국어 (English) format, e.g. 작업증명 (Proof of Work)
- Each part MUST be 100-130 words (Korean words) - this is critical for 60-second timing
- Each part should be a COMPLETE standalone script that makes sense on its own
- Each part starts with a hook that grabs attention in the first 3 seconds
- Each part ends with a call-to-action: "다음 파트도 놓치지 마세요!" or "구독하고 더 알아보세요!"
- Tone: conversational, engaging, easy to understand
- Write as spoken word for TTS narration - natural Korean speech
- Do NOT use hashtags, emojis, or markdown formatting within scripts
- Do NOT use bullet points or numbered lists within scripts - write flowing sentences
- IMPORTANT: For readability, break the script into short paragraphs (2-3 sentences each) with blank lines between them. Do NOT write one giant paragraph.

Output format - use EXACTLY this structure:

## Part 1: [파트 제목]

[나레이션 스크립트 - 2~3문장마다 줄바꿈]

## Part 2: [파트 제목]

[나레이션 스크립트 - 2~3문장마다 줄바꿈]

Continue until you have covered the topic thoroughly. You MUST write at least 4 parts, ideally 5. Each part explores a different angle or sub-topic."""


def generate_article(topic: str, slug: str, category: str) -> Path:
    """Generate a multi-part Shorts article about a Bitcoin topic."""
    prompt = f"{ARTICLE_PROMPT}\n\nTopic: {topic}"
    content = _call_gemini(prompt, max_tokens=8000)

    # Count parts
    parts = [p for p in content.split("## Part") if p.strip()]
    num_parts = len(parts)

    # Build frontmatter
    md = f"""---
title: "{topic}"
category: {category}
slug: {slug}
parts: {num_parts}
---

{content}
"""

    # Save to category folder
    output_dir = KNOWLEDGE_DIR / category
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}.md"
    output_path.write_text(md, encoding="utf-8")

    print(f"[OK] {category}/{slug}.md ({num_parts} parts)")
    return output_path


def list_topics():
    """List all available topics by category."""
    for category, topics in TOPICS.items():
        print(f"\n=== {category.upper()} ===")
        for topic, slug in topics:
            path = KNOWLEDGE_DIR / category / f"{slug}.md"
            if path.exists():
                # Count parts in existing file
                text = path.read_text(encoding="utf-8")
                parts = text.count("## Part")
                print(f"  [v] {topic} ({parts} parts)")
            else:
                print(f"  [ ] {topic}")


def list_existing():
    """List already generated articles."""
    count = 0
    for category in TOPICS:
        cat_dir = KNOWLEDGE_DIR / category
        if cat_dir.exists():
            for md in sorted(cat_dir.glob("*.md")):
                count += 1
    return count


def pick_random(category: str = None) -> tuple:
    """Pick a random topic, optionally from a specific category."""
    if category and category in TOPICS:
        pool = TOPICS[category]
    else:
        pool = [item for topics in TOPICS.values() for item in topics]
        category = None

    available = []
    for topic, slug in pool:
        cat = category
        if not cat:
            for c, topics in TOPICS.items():
                if (topic, slug) in topics:
                    cat = c
                    break
        path = KNOWLEDGE_DIR / cat / f"{slug}.md"
        if not path.exists():
            available.append((topic, slug, cat))

    if not available:
        print("[INFO] All topics in this category already generated!")
        return None

    return random.choice(available)


def main():
    parser = argparse.ArgumentParser(description="Bitcoin Knowledge Article Generator")
    parser.add_argument("--topic", type=str, help="Specific topic to write about")
    parser.add_argument("--category", type=str, choices=list(TOPICS.keys()),
                        help="Generate from specific category")
    parser.add_argument("--list", action="store_true", help="List all topics")
    parser.add_argument("--batch", type=int, help="Generate N random topics")
    args = parser.parse_args()

    if args.list:
        list_topics()
        total = list_existing()
        all_topics = sum(len(t) for t in TOPICS.values())
        print(f"\nGenerated: {total}/{all_topics} topics")
        return

    if args.topic:
        slug = None
        category = args.category or "basics"
        for cat, topics in TOPICS.items():
            for t, s in topics:
                if t == args.topic:
                    slug = s
                    category = cat
                    break
        if not slug:
            slug = re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-")
            if not slug:
                from datetime import datetime
                slug = f"article-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        generate_article(args.topic, slug, category)
        return

    if args.batch:
        for i in range(args.batch):
            result = pick_random(args.category)
            if not result:
                break
            topic, slug, cat = result
            print(f"\n[{i+1}/{args.batch}] {topic}")
            generate_article(topic, slug, cat)
        return

    result = pick_random(args.category)
    if result:
        topic, slug, cat = result
        print(f"Generating: {topic}")
        generate_article(topic, slug, cat)


if __name__ == "__main__":
    main()
