"""
Send URL_DELETED to Google Indexing API for all unpublished articles.

Queries Supabase for articles with published=false and sends
URL_DELETED notification so Google removes them from its index faster.

Usage:
  cd backend && python -m scripts.cleanup_deleted
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"


def cleanup_deleted():
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

    if not supabase_url or not supabase_key:
        logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not set.")
        return

    from supabase import create_client

    supabase = create_client(supabase_url, supabase_key)

    # Get all unpublished articles
    result = supabase.table("articles").select("slug").eq("published", False).execute()
    unpublished = result.data or []

    logger.info(f"Found {len(unpublished)} unpublished articles")

    if not unpublished:
        logger.info("No unpublished articles to clean up.")
        return

    urls = [f"{SITE_URL}/article/{a['slug']}" for a in unpublished]

    for url in urls:
        logger.info(f"  - {url}")

    # Send URL_DELETED via Google Indexing API
    if not sa_json:
        logger.warning("GOOGLE_INDEXING_SA_KEY not set. Skipping Indexing API calls.")
        return

    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    import requests

    SCOPES = ["https://www.googleapis.com/auth/indexing"]
    info = json.loads(sa_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

    success = 0
    failed = 0
    for url in urls:
        try:
            resp = requests.post(
                "https://indexing.googleapis.com/v3/urlNotifications:publish",
                headers=headers,
                json={"url": url, "type": "URL_DELETED"},
                timeout=10,
            )
            if resp.status_code == 200:
                success += 1
                logger.info(f"URL_DELETED sent: {url}")
            else:
                failed += 1
                logger.warning(f"Failed ({resp.status_code}): {url} - {resp.text[:100]}")
        except Exception as e:
            failed += 1
            logger.error(f"Error for {url}: {e}")

    logger.info(f"\nDone: {success} succeeded, {failed} failed out of {len(urls)} URLs")


if __name__ == "__main__":
    cleanup_deleted()
