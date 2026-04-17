"""
Daily indexing pipeline: submit pending articles to Google Indexing API.

Reads articles where indexing_submitted_at IS NULL, submits up to the
per-day quota (default 180, leaving headroom below Google's 200 limit),
marks successful ones so tomorrow's run picks up the rest, and stops
early on 429 quota exhaustion.

Usage:
    python -m scripts.index_pending [--limit 180] [--dry-run]

Environment:
    SUPABASE_URL, SUPABASE_SERVICE_KEY
    GOOGLE_INDEXING_SA_KEY (JSON string)
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import requests
from google.auth.transport.requests import Request
from supabase import create_client

from scripts.notify_indexing import INDEXING_API_URL, _get_credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=180,
                        help="Max URLs to submit (default 180, under the 200/day quota)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List pending articles but skip API calls and updates")
    args = parser.parse_args()

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    supabase = create_client(url, key)

    pending = (
        supabase.table("articles")
        .select("id, slug")
        .eq("published", True)
        .is_("indexing_submitted_at", "null")
        .order("created_at", desc=True)
        .limit(args.limit)
        .execute()
    )

    rows = pending.data or []
    logger.info(f"Pending articles: {len(rows)}")
    if not rows:
        logger.info("Nothing to submit. Done.")
        return 0

    if args.dry_run:
        logger.info("Dry-run. Sample URLs:")
        for row in rows[:10]:
            logger.info(f"  {SITE_URL}/article/{row['slug']}")
        return 0

    credentials = _get_credentials()
    if credentials is None:
        logger.error("GOOGLE_INDEXING_SA_KEY not configured. Aborting.")
        return 1

    credentials.refresh(Request())
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}",
    }

    succeeded = 0
    failed = 0
    quota_hit = False

    for row in rows:
        article_url = f"{SITE_URL}/article/{row['slug']}"
        payload = {"url": article_url, "type": "URL_UPDATED"}

        try:
            resp = requests.post(INDEXING_API_URL, json=payload, headers=headers, timeout=10)
        except Exception as e:
            logger.warning(f"  ERROR {article_url}: {e}")
            failed += 1
            continue

        if resp.status_code == 200:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                supabase.table("articles").update({
                    "indexing_submitted_at": now_iso,
                }).eq("id", row["id"]).execute()
                succeeded += 1
                logger.info(f"  OK {row['slug']}")
            except Exception as e:
                logger.warning(f"  DB update failed {row['slug']}: {e}")
                failed += 1
        elif resp.status_code == 429:
            logger.info(f"  429 quota exceeded — stopping. {article_url}")
            quota_hit = True
            break
        else:
            logger.warning(f"  {resp.status_code} {article_url}: {resp.text[:200]}")
            failed += 1

    total_pending = len(rows)
    logger.info(f"\n=== Result ===")
    logger.info(f"Submitted: {succeeded} / {total_pending} processed")
    logger.info(f"Failed: {failed}")
    logger.info(f"Quota exhausted: {quota_hit}")
    logger.info(f"Rows remaining in DB with NULL flag will be picked up tomorrow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
