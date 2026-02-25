"""
Google Search Console sitemap submission.

Submits sitemaps via the Search Console API so Google
re-reads them immediately after new articles are published.

Usage:
  cd backend && python -m scripts.submit_sitemaps
"""

import json
import logging
import os
import sys
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"
# Search Console 도메인 속성 (sc-domain: 형식)
SC_SITE = "sc-domain:nexustopic.com"
SITEMAPS = [
    f"{SITE_URL}/sitemap.xml",
    f"{SITE_URL}/news-sitemap.xml",
]

SCOPES = ["https://www.googleapis.com/auth/webmasters"]


def submit_sitemaps():
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    if not sa_json:
        logger.warning("GOOGLE_INDEXING_SA_KEY not set. Skipping sitemap submission.")
        return

    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        import requests

        info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        credentials.refresh(Request())

        headers = {"Authorization": f"Bearer {credentials.token}"}
        encoded_site = quote(SC_SITE, safe="")

        for sitemap_url in SITEMAPS:
            encoded_sitemap = quote(sitemap_url, safe="")
            api_url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps/{encoded_sitemap}"

            resp = requests.put(api_url, headers=headers, timeout=10)
            if resp.status_code in (200, 204):
                logger.info(f"Submitted: {sitemap_url}")
            else:
                logger.warning(f"Failed ({resp.status_code}): {sitemap_url} - {resp.text[:200]}")

    except Exception as e:
        logger.error(f"Sitemap submission failed: {e}")


if __name__ == "__main__":
    submit_sitemaps()
