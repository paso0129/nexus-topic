"""
Remove AI disclosure paragraphs from all published articles.

Strips <p class="ai-disclosure">...</p> from article content.

Usage:
  python -m scripts.remove_ai_disclosure
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

DISCLOSURE_PATTERN = re.compile(
    r'\s*<p\s+class=["\']ai-disclosure["\']>.*?</p>\s*',
    re.DOTALL,
)


def main() -> None:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    result = (
        supabase.table("articles")
        .select("id, slug, content")
        .eq("published", True)
        .execute()
    )
    articles = result.data or []
    logger.info("Total published articles: %d", len(articles))

    updated = 0
    for a in articles:
        content = a.get("content", "") or ""
        if "ai-disclosure" not in content:
            continue

        cleaned = DISCLOSURE_PATTERN.sub("", content).rstrip()
        if cleaned == content:
            continue

        supabase.table("articles").update({"content": cleaned}).eq("id", a["id"]).execute()
        updated += 1
        logger.info("  Removed disclosure: slug=%s", a.get("slug", ""))

    logger.info("Updated %d articles (removed AI disclosure)", updated)


if __name__ == "__main__":
    main()
