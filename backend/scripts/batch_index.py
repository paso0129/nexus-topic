#!/usr/bin/env python3
"""
One-off script: Send Google Indexing API notifications for existing articles.
Usage: cd backend && python -m scripts.batch_index --limit 120
"""

import argparse
import logging
import sys
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"


def fetch_recent_slugs(limit: int) -> list[str]:
    """Fetch the most recent article slugs from Supabase."""
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        sys.exit(1)

    client = create_client(url, key)
    resp = (
        client.table("articles")
        .select("slug")
        .eq("published", True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [row["slug"] for row in resp.data]


def main():
    parser = argparse.ArgumentParser(description="Batch index existing articles")
    parser.add_argument("--limit", type=int, default=120, help="Number of recent articles")
    args = parser.parse_args()

    logger.info(f"Fetching {args.limit} most recent article slugs from Supabase...")
    slugs = fetch_recent_slugs(args.limit)
    logger.info(f"Found {len(slugs)} articles")

    if not slugs:
        logger.info("No articles to index.")
        return

    urls = [f"{SITE_URL}/article/{slug}" for slug in slugs]

    from scripts.notify_indexing import notify_urls

    logger.info(f"Sending indexing notifications for {len(urls)} URLs...")
    result = notify_urls(urls)
    logger.info(
        f"Done: {result['success']} succeeded, {result['failed']} failed"
    )
    if result["errors"]:
        logger.info("Errors:")
        for err in result["errors"]:
            logger.info(f"  - {err}")


if __name__ == "__main__":
    main()
