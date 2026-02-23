"""
Google Search Console Search Analytics query.

Fetches performance data (clicks, impressions, CTR, position)
for the site from the last 28 days.

Usage:
  cd backend && python -m scripts.search_analytics
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
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def query_search_analytics():
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    if not sa_json:
        logger.error("GOOGLE_INDEXING_SA_KEY not set.")
        return

    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    import requests
    from datetime import datetime, timedelta

    info = json.loads(sa_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }
    encoded_site = quote(f"{SITE_URL}/", safe="")
    api_url = f"https://www.googleapis.com/webmasters/v3/sites/{encoded_site}/searchAnalytics/query"

    end_date = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    # 1) Top queries by impressions
    logger.info(f"=== Search Analytics: {start_date} ~ {end_date} ===\n")

    resp = requests.post(
        api_url,
        headers=headers,
        json={
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query"],
            "rowLimit": 25,
            "dataState": "all",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        logger.error(f"API error ({resp.status_code}): {resp.text[:500]}")
        return

    data = resp.json()
    rows = data.get("rows", [])

    logger.info("📊 TOP QUERIES (by impressions):")
    logger.info(f"{'Query':<60} {'Clicks':>7} {'Impr':>7} {'CTR':>7} {'Pos':>7}")
    logger.info("-" * 92)
    for row in rows:
        q = row["keys"][0][:58]
        logger.info(
            f"{q:<60} {row['clicks']:>7.0f} {row['impressions']:>7.0f} "
            f"{row['ctr']*100:>6.1f}% {row['position']:>6.1f}"
        )

    # 2) Top pages by impressions
    resp2 = requests.post(
        api_url,
        headers=headers,
        json={
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["page"],
            "rowLimit": 25,
            "dataState": "all",
        },
        timeout=30,
    )

    if resp2.status_code == 200:
        data2 = resp2.json()
        rows2 = data2.get("rows", [])
        logger.info(f"\n📄 TOP PAGES (by impressions):")
        logger.info(f"{'Page':<70} {'Clicks':>7} {'Impr':>7} {'CTR':>7} {'Pos':>7}")
        logger.info("-" * 102)
        for row in rows2:
            p = row["keys"][0].replace(SITE_URL, "")[:68]
            logger.info(
                f"{p:<70} {row['clicks']:>7.0f} {row['impressions']:>7.0f} "
                f"{row['ctr']*100:>6.1f}% {row['position']:>6.1f}"
            )

    # 3) Overall totals
    resp3 = requests.post(
        api_url,
        headers=headers,
        json={
            "startDate": start_date,
            "endDate": end_date,
            "dataState": "all",
        },
        timeout=30,
    )

    if resp3.status_code == 200:
        data3 = resp3.json()
        rows3 = data3.get("rows", [])
        if rows3:
            r = rows3[0]
            logger.info(f"\n📈 TOTALS ({start_date} ~ {end_date}):")
            logger.info(f"  Clicks: {r['clicks']:.0f}")
            logger.info(f"  Impressions: {r['impressions']:.0f}")
            logger.info(f"  CTR: {r['ctr']*100:.2f}%")
            logger.info(f"  Avg Position: {r['position']:.1f}")


if __name__ == "__main__":
    query_search_analytics()
