"""
One-off script: Fix incorrect streaming service prices in a specific article.

Usage (via GitHub Actions):
  python -m scripts.fix_article_prices

Target article: best-streaming-credit-cards-a-skeptics-march-2026-guide
"""

import logging
import os
import re
import sys

from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SLUG = "best-streaming-credit-cards-a-skeptics-march-2026-guide"

# (old_text, new_text) — order matters for the total line
REPLACEMENTS = [
    # Netflix: $22.99 was pre-2025 Premium price, now $24.99
    ("Netflix ($22.99)", "Netflix ($24.99)"),
    # Max: $16.99 tier doesn't exist; Standard is $18.49
    ("Max ($16.99)", "Max ($18.49)"),
    # Paramount+ with Showtime: raised to $13.99 in Jan 2026
    ("Paramount+ with Showtime ($11.99)", "Paramount+ with Showtime ($13.99)"),
    # Peacock Premium: $5.99 is student-only; actual is $10.99/mo (with ads)
    ("Peacock Premium ($5.99)", "Peacock Premium ($10.99)"),
]

# The old total was ~$77.95 based on the wrong prices.
# Correct total: $24.99 + $19.99 + $18.49 + $13.99 + $10.99 = $88.45
TOTAL_REPLACEMENTS = [
    ("comfortably past $75 a month", "closing in on $90 a month"),
    ("$75+ monthly", "$88+ monthly"),
    ("$75 a month", "$88 a month"),
    ("past $75", "past $88"),
]


def main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        sys.exit(1)

    client = create_client(url, key)

    # Fetch article
    result = client.table("articles").select("id, content").eq("slug", SLUG).execute()
    if not result.data:
        logger.error(f"Article not found: {SLUG}")
        sys.exit(1)

    article = result.data[0]
    content = article["content"]
    original = content

    # Apply price replacements
    for old, new in REPLACEMENTS:
        if old in content:
            content = content.replace(old, new)
            logger.info(f"Replaced: {old} -> {new}")
        else:
            logger.warning(f"Not found in content: {old}")

    # Apply total replacements
    for old, new in TOTAL_REPLACEMENTS:
        if old in content:
            content = content.replace(old, new)
            logger.info(f"Replaced total: {old} -> {new}")

    if content == original:
        logger.info("No changes needed — content already correct")
        return

    # Update article
    client.table("articles").update({"content": content}).eq("slug", SLUG).execute()
    logger.info(f"Article updated successfully: {SLUG}")


if __name__ == "__main__":
    main()
