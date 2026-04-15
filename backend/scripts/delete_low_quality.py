"""
Delete low-quality articles from Supabase.

Criteria: <500 words AND 0 external source links.
Uses audit_articles logic for consistency.

Usage:
  python -m scripts.delete_low_quality
"""
import os
import re
import logging

from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

WORD_THRESHOLD = 500
MIN_SOURCES = 1


def count_words(html: str) -> int:
    text = re.sub(r"<[^>]+>", "", html)
    return len(text.split())


def count_source_links(html: str) -> int:
    return len(re.findall(r'<a\s+[^>]*href=["\']https?://', html))


def main() -> None:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    result = (
        supabase.table("articles")
        .select("id, slug, title, content")
        .eq("published", True)
        .execute()
    )
    articles = result.data or []
    logger.info("Total published articles: %d", len(articles))

    to_delete = []
    for a in articles:
        content = a.get("content", "") or ""
        wc = count_words(content)
        sources = count_source_links(content)
        if wc < WORD_THRESHOLD and sources < MIN_SOURCES:
            to_delete.append({
                "id": a["id"],
                "slug": a.get("slug", ""),
                "title": (a.get("title", "") or "")[:60],
                "word_count": wc,
                "sources": sources,
            })

    logger.info("Found %d delete candidates (<500w + 0 sources)", len(to_delete))

    for item in to_delete:
        logger.info(
            "  Deleting slug=%s | %dw | %s",
            item["slug"],
            item["word_count"],
            item["title"],
        )
        supabase.table("articles").delete().eq("id", item["id"]).execute()

    logger.info("Deleted %d low-quality articles", len(to_delete))


if __name__ == "__main__":
    main()
