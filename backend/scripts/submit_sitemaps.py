"""
Google Search Console sitemap submission + verification.

Submits sitemaps via the Search Console API, then verifies
Google actually processed them by checking the URL count.

Usage:
  cd backend && python -m scripts.submit_sitemaps
"""

import json
import logging
import os
import sys
import time
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


def _get_credentials():
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    if not sa_json:
        raise RuntimeError("GOOGLE_INDEXING_SA_KEY not set")

    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    info = json.loads(sa_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    credentials.refresh(Request())
    return credentials


def _submit(headers, encoded_site):
    """Submit sitemaps to Search Console."""
    import requests

    success = 0
    for sitemap_url in SITEMAPS:
        encoded_sitemap = quote(sitemap_url, safe="")
        api_url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps/{encoded_sitemap}"

        resp = requests.put(api_url, headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            logger.info(f"Submitted: {sitemap_url}")
            success += 1
        else:
            logger.warning(f"Failed ({resp.status_code}): {sitemap_url} - {resp.text[:200]}")

    return success


def _verify(headers, encoded_site):
    """Verify sitemaps were processed by checking URL counts."""
    import requests

    api_url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/sitemaps"
    resp = requests.get(api_url, headers=headers, timeout=10)

    if resp.status_code != 200:
        logger.warning(f"Verification failed ({resp.status_code}): {resp.text[:200]}")
        return

    data = resp.json()
    sitemaps = data.get("sitemap", [])

    for sm in sitemaps:
        path = sm.get("path", "")
        submitted = sm.get("contents", [{}])[0].get("submitted", "?")
        indexed = sm.get("contents", [{}])[0].get("indexed", "?")
        last_downloaded = sm.get("lastDownloaded", "never")
        warnings_count = int(sm.get("warnings", 0))
        errors_count = int(sm.get("errors", 0))

        status = "❌" if errors_count > 0 else "⚠️" if warnings_count > 0 else "✅"
        logger.info(
            f"{status} {path} — "
            f"submitted: {submitted}, indexed: {indexed}, "
            f"last fetched: {last_downloaded}, "
            f"warnings: {warnings_count}, errors: {errors_count}"
        )


def submit_sitemaps():
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    if not sa_json:
        logger.warning("GOOGLE_INDEXING_SA_KEY not set. Skipping sitemap submission.")
        return

    try:
        credentials = _get_credentials()
        headers = {"Authorization": f"Bearer {credentials.token}"}
        encoded_site = quote(SC_SITE, safe="")

        # 1. Submit
        success = _submit(headers, encoded_site)
        logger.info(f"Submission complete: {success}/{len(SITEMAPS)} succeeded")

        # 2. Wait for Google to process
        time.sleep(5)

        # 3. Verify
        logger.info("Verifying sitemap status...")
        _verify(headers, encoded_site)

    except Exception as e:
        logger.error(f"Sitemap submission failed: {e}")


if __name__ == "__main__":
    submit_sitemaps()
