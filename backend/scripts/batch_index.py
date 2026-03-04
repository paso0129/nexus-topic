#!/usr/bin/env python3
"""
Google Indexing API batch notification tool.

Sends URL_UPDATED for current articles and static pages,
and URL_DELETED for removed articles.

Usage:
  cd backend && python -m scripts.batch_index                    # Index ALL articles + static pages
  cd backend && python -m scripts.batch_index --recent 24        # Index articles created/updated in last 24 hours
  cd backend && python -m scripts.batch_index --deleted SLUG1 SLUG2  # Notify deleted URLs
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

# Static pages that should always be indexed
STATIC_PAGES = [
    "",              # homepage
    "/about",
    "/contact",
    "/terms",
    "/privacy",
    "/archive",
    "/search",
]


def fetch_current_slugs(recent_hours: int = None) -> list[str]:
    """Fetch article slugs from Supabase.

    Args:
        recent_hours: If set, only return articles created/updated in the last N hours.
    """
    from datetime import datetime, timedelta, timezone
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        sys.exit(1)

    client = create_client(url, key)
    query = (
        client.table("articles")
        .select("slug")
        .eq("published", True)
    )

    if recent_hours:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=recent_hours)).isoformat()
        # updated_at >= cutoff OR created_at >= cutoff
        query = query.or_(f"updated_at.gte.{cutoff},created_at.gte.{cutoff}")
        logger.info(f"Filtering articles updated/created since {cutoff}")

    resp = query.order("created_at", desc=True).execute()
    return [row["slug"] for row in resp.data]


def main():
    parser = argparse.ArgumentParser(description="Batch index articles via Google Indexing API")
    parser.add_argument("--deleted", nargs="*", default=None,
                        help="Slugs of deleted articles to send URL_DELETED for")
    parser.add_argument("--deleted-urls", nargs="*", default=None,
                        help="Full URLs of deleted pages to send URL_DELETED for")
    parser.add_argument("--recent", type=int, default=None, metavar="HOURS",
                        help="Only index articles created/updated in the last N hours")
    parser.add_argument("--skip-static", action="store_true",
                        help="Skip indexing static pages")
    args = parser.parse_args()

    from scripts.notify_indexing import notify_urls

    # 1. Index current articles (URL_UPDATED)
    if args.recent:
        logger.info(f"Fetching articles updated in the last {args.recent} hours...")
    else:
        logger.info("Fetching all current article slugs from Supabase...")
    slugs = fetch_current_slugs(recent_hours=args.recent)
    logger.info(f"Found {len(slugs)} current articles")

    update_urls = [f"{SITE_URL}/article/{slug}" for slug in slugs]

    # Add static pages
    if not args.skip_static:
        static_urls = [f"{SITE_URL}{page}" for page in STATIC_PAGES]
        update_urls.extend(static_urls)
        logger.info(f"Added {len(static_urls)} static pages")

    # Add category pages
    categories = ["it-biz", "culture", "economy", "entertainment",
                   "gaming", "health", "policy", "science", "tech"]
    cat_urls = [f"{SITE_URL}/category/{cat}" for cat in categories]
    update_urls.extend(cat_urls)
    logger.info(f"Added {len(cat_urls)} category pages")

    logger.info(f"\nSending URL_UPDATED for {len(update_urls)} URLs...")
    result = notify_urls(update_urls, "URL_UPDATED")
    logger.info(f"URL_UPDATED: {result['success']} succeeded, {result['failed']} failed")

    # 2. Notify deleted URLs (URL_DELETED)
    delete_urls = []
    if args.deleted:
        delete_urls.extend([f"{SITE_URL}/article/{slug}" for slug in args.deleted])
    if args.deleted_urls:
        delete_urls.extend(args.deleted_urls)

    if delete_urls:
        logger.info(f"\nSending URL_DELETED for {len(delete_urls)} URLs...")
        del_result = notify_urls(delete_urls, "URL_DELETED")
        logger.info(f"URL_DELETED: {del_result['success']} succeeded, {del_result['failed']} failed")

    # Summary
    logger.info("\n=== Indexing Summary ===")
    logger.info(f"Articles indexed: {len(slugs)}")
    logger.info(f"Static pages: {len(STATIC_PAGES) + len(categories)}")
    logger.info(f"Deleted URLs notified: {len(delete_urls)}")
    if result["errors"]:
        logger.info("Errors:")
        for err in result["errors"][:10]:
            logger.info(f"  - {err}")


if __name__ == "__main__":
    main()
