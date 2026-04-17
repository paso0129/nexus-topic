"""
Retrofit "핵심 3줄 요약" section into existing articles.

For every published article:
  1. Strip any pre-existing <div class="article-sources">…</div> block.
  2. Strip any pre-existing <div class="article-summary">…</div> block (idempotent rerun).
  3. Ask Claude Haiku to generate three one-line summary sentences grounded in the
     article's own body text (no new facts).
  4. Append the new `.article-summary` block at the very end of the content.

Usage:
    python -m scripts.add_three_line_summary --dry-run
    python -m scripts.add_three_line_summary --apply
    python -m scripts.add_three_line_summary --apply --limit 50
    python -m scripts.add_three_line_summary --apply --only-missing

Environment:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import anthropic
from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SOURCES_BLOCK_RE = re.compile(
    r'<div\s+class=["\']article-sources["\'][^>]*>.*?</div>\s*',
    re.IGNORECASE | re.DOTALL,
)
SUMMARY_BLOCK_RE = re.compile(
    r'<div\s+class=["\']article-summary["\'][^>]*>.*?</div>\s*',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")

SUMMARY_PROMPT = """다음 한국어 뉴스 기사의 본문을 읽고 "핵심 3줄 요약"을 작성하세요.

제목: {title}

본문 (HTML 태그는 무시하고 내용만 참고):
{body}

작성 규칙:
1. 본문에 실제로 나온 사실만 사용하세요. 새 정보·추측·가정을 절대 추가하지 마세요.
2. 3문장, 각 문장 40~70자, 한 줄에서 완결되어야 합니다.
3. 수동태와 추상 표현(“주목된다”, “지켜봐야 한다”, “결론적으로”) 금지. 구체 주체·수치·연도를 포함하세요.
4. 1번: 기사가 전하는 가장 중요한 사실
   2번: 배경 또는 파급 효과
   3번: 독자에게 의미 있는 시사점
5. 각 문장은 독립적으로 읽어도 이해 가능해야 합니다.

응답 형식 (다른 말 없이 정확히 이 형식으로만):
1. [첫 번째 문장]
2. [두 번째 문장]
3. [세 번째 문장]
"""


def strip_legacy_blocks(html: str) -> str:
    """Remove old sources/summary blocks so retries stay idempotent."""
    cleaned = SOURCES_BLOCK_RE.sub("", html)
    cleaned = SUMMARY_BLOCK_RE.sub("", cleaned)
    return cleaned.rstrip() + "\n"


def render_summary_html(sentences: list[str]) -> str:
    safe = [s.strip() for s in sentences if s.strip()]
    lis = "\n".join(f"<li>{s}</li>" for s in safe[:3])
    return (
        '<div class="article-summary">\n'
        "<h3>📌 핵심 3줄 요약</h3>\n"
        "<ol>\n"
        f"{lis}\n"
        "</ol>\n"
        "</div>"
    )


def parse_summary_response(raw: str) -> list[str]:
    sentences: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(?:\d+[.)]|[-*•])\s*(.+)$", line)
        if m:
            sentences.append(m.group(1).strip())
        elif sentences and len(sentences) < 3:
            sentences[-1] += " " + line
    return sentences[:3]


def generate_summary(
    client: anthropic.Anthropic,
    title: str,
    body_text: str,
) -> Optional[list[str]]:
    prompt = SUMMARY_PROMPT.format(title=title, body=body_text[:6000])
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.error(f"  Claude error: {e}")
        return None

    raw = resp.content[0].text.strip()
    sentences = parse_summary_response(raw)
    if len(sentences) != 3:
        logger.warning(f"  Unexpected summary format ({len(sentences)} lines): {raw[:160]!r}")
        return None
    if any(len(s) < 10 for s in sentences):
        logger.warning(f"  Summary line too short: {sentences}")
        return None
    return sentences


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N articles (0=all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N articles")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip articles that already contain an article-summary block",
    )
    parser.add_argument("--sleep", type=float, default=0.6, help="Sleep seconds between API calls")
    args = parser.parse_args()

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    page_size = 1000
    rows: list[dict] = []
    offset = 0
    while True:
        res = (
            supabase.table("articles")
            .select("id, slug, title, content")
            .eq("published", True)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    logger.info(f"Published articles fetched: {len(rows)}")

    if args.offset:
        rows = rows[args.offset:]
    if args.limit > 0:
        rows = rows[: args.limit]

    logger.info(f"Scope after offset/limit: {len(rows)}")

    processed = updated = skipped = failed = 0

    for idx, row in enumerate(rows, start=1):
        slug = row["slug"]
        title = row.get("title") or ""
        content = row.get("content") or ""
        has_summary = bool(SUMMARY_BLOCK_RE.search(content))
        has_sources = bool(SOURCES_BLOCK_RE.search(content))

        if args.only_missing and has_summary:
            skipped += 1
            continue

        body_text = TAG_RE.sub(" ", content)
        body_text = re.sub(r"\s+", " ", body_text).strip()
        if len(body_text) < 200:
            logger.warning(f"[{idx}/{len(rows)}] {slug}: body too short ({len(body_text)}ch), skip")
            skipped += 1
            continue

        logger.info(
            f"[{idx}/{len(rows)}] {slug} "
            f"(sources={'Y' if has_sources else 'N'}, summary={'Y' if has_summary else 'N'})"
        )

        sentences = generate_summary(client, title, body_text)
        if not sentences:
            failed += 1
            time.sleep(args.sleep)
            continue

        new_content = strip_legacy_blocks(content) + "\n" + render_summary_html(sentences) + "\n"

        if args.apply:
            try:
                supabase.table("articles").update({"content": new_content}).eq("id", row["id"]).execute()
                updated += 1
                logger.info(f"  OK: {sentences[0][:60]}…")
            except Exception as e:
                logger.error(f"  DB update failed: {e}")
                failed += 1
        else:
            logger.info(f"  DRY: {sentences[0][:60]}…")
            updated += 1

        processed += 1
        time.sleep(args.sleep)

    logger.info("=== Result ===")
    logger.info(f"Processed: {processed}")
    logger.info(f"Updated:   {updated}{' (dry-run)' if not args.apply else ''}")
    logger.info(f"Skipped:   {skipped}")
    logger.info(f"Failed:    {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
