"""
IndexNow + WebSub notification module.

- IndexNow: Instantly notifies Bing, Yandex, Naver, Seznam
- WebSub: Pings PubSubHubbub hub to push RSS updates to subscribers (incl. Google)

Usage:
  cd backend && python -m scripts.notify_search_engines
  cd backend && python -m scripts.notify_search_engines --urls https://example.com/article/slug
"""

import argparse
import logging
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"
INDEXNOW_KEY = "777cae98ed26453e9fcc8c99e6773d8d"
WEBSUB_HUB = "https://pubsubhubbub.appspot.com/"
FEED_URL = f"{SITE_URL}/feed.xml"


def notify_indexnow(urls: list[str]):
    """Submit URLs to IndexNow (Bing, Yandex, Naver, Seznam)."""
    if not urls:
        logger.info("IndexNow: No URLs to submit")
        return

    payload = {
        "host": "www.nexustopic.com",
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": urls[:10000],
    }

    try:
        resp = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code in (200, 202):
            logger.info(f"IndexNow: Submitted {len(urls)} URLs successfully")
        else:
            logger.warning(f"IndexNow: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        logger.error(f"IndexNow: Failed - {e}")


def ping_websub():
    """Ping PubSubHubbub hub to notify RSS subscribers."""
    try:
        resp = requests.post(
            WEBSUB_HUB,
            data={
                "hub.mode": "publish",
                "hub.url": FEED_URL,
            },
            timeout=10,
        )
        if resp.status_code == 204:
            logger.info(f"WebSub: Hub pinged successfully for {FEED_URL}")
        else:
            logger.warning(f"WebSub: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        logger.error(f"WebSub: Failed - {e}")


def main():
    parser = argparse.ArgumentParser(description="Notify search engines (IndexNow + WebSub)")
    parser.add_argument("--urls", nargs="*", default=None,
                        help="Specific URLs to submit to IndexNow")
    args = parser.parse_args()

    # If specific URLs given, use those. Otherwise fetch all from Supabase.
    if args.urls:
        urls = args.urls
    else:
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
            .execute()
        )
        urls = [f"{SITE_URL}/article/{row['slug']}" for row in resp.data]
        # Add static + category pages
        urls.append(SITE_URL)
        for cat in ["it-biz", "culture", "economy", "entertainment",
                     "gaming", "health", "policy", "science", "security", "tech"]:
            urls.append(f"{SITE_URL}/category/{cat}")

    logger.info(f"=== Search Engine Notifications ===")
    logger.info(f"URLs to submit: {len(urls)}")

    notify_indexnow(urls)
    ping_websub()

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
