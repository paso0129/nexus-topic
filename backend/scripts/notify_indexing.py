"""
Google Indexing API notification module.

Sends URL_UPDATED notifications to Google's Indexing API
so that newly published articles are crawled and indexed promptly.
"""

import json
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

INDEXING_API_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
MAX_BATCH_SIZE = 200


def _get_credentials():
    """Load service account credentials from GOOGLE_INDEXING_SA_KEY env var."""
    sa_json = os.getenv("GOOGLE_INDEXING_SA_KEY")
    if not sa_json:
        return None

    try:
        from google.oauth2 import service_account

        info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return credentials
    except Exception as e:
        logger.warning(f"Failed to load indexing service account credentials: {e}")
        return None


def notify_urls(urls: List[str], notification_type: str = "URL_UPDATED") -> dict:
    """
    Send notifications to Google Indexing API.

    Args:
        urls: List of full URLs to notify
        notification_type: "URL_UPDATED" or "URL_DELETED"

    Returns:
        dict with 'success' count, 'failed' count, and 'errors' list
    """
    if not urls:
        return {"success": 0, "failed": 0, "errors": []}

    if notification_type not in ("URL_UPDATED", "URL_DELETED"):
        return {"success": 0, "failed": 0, "errors": [f"Invalid type: {notification_type}"]}

    credentials = _get_credentials()
    if credentials is None:
        logger.warning("Google Indexing API credentials not configured. Skipping.")
        return {"success": 0, "failed": 0, "errors": ["No credentials"]}

    import requests
    from google.auth.transport.requests import Request

    # Refresh the access token
    credentials.refresh(Request())
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}",
    }

    batch = urls[:MAX_BATCH_SIZE]
    success = 0
    failed = 0
    errors = []

    for url in batch:
        try:
            payload = {"url": url, "type": notification_type}
            resp = requests.post(INDEXING_API_URL, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                success += 1
                logger.info(f"  {notification_type}: {url}")
            else:
                failed += 1
                msg = f"{url} → HTTP {resp.status_code}: {resp.text[:200]}"
                errors.append(msg)
                logger.warning(f"  Failed: {msg}")
        except Exception as e:
            failed += 1
            msg = f"{url} → {e}"
            errors.append(msg)
            logger.warning(f"  Error: {msg}")

    return {"success": success, "failed": failed, "errors": errors}
