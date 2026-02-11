"""
Backfill Missing Article Images

Finds published articles without a featured_image and fetches one from Unsplash.
Reuses the existing image search logic from fetch_images.py.

Usage:
    python -m scripts.backfill_images
"""

import time
import logging

from dotenv import load_dotenv

load_dotenv()

from scripts.database import get_db_client, is_supabase_enabled
from scripts.fetch_images import _build_search_query, fetch_unsplash_image

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_images() -> int:
    """
    Find articles without featured images and fetch images from Unsplash.

    Returns:
        Number of articles updated
    """
    if not is_supabase_enabled():
        logger.error("Supabase is not enabled. Set USE_SUPABASE=true in .env")
        return 0

    db = get_db_client()
    articles = db.list_articles_without_images()

    if not articles:
        logger.info("All articles already have images. Nothing to backfill.")
        return 0

    logger.info(f"Found {len(articles)} articles without images")
    updated = 0

    for i, article in enumerate(articles):
        slug = article.get('slug', '')
        title = article.get('title', '')
        logger.info(f"[{i+1}/{len(articles)}] Processing: {title}")

        query = _build_search_query(article)
        logger.info(f"  Search query: '{query}'")

        result = fetch_unsplash_image(query)

        if result:
            updates = {
                'featured_image': result['url'],
                'image_attribution': {
                    'photographer_name': result['photographer_name'],
                    'photographer_url': result['photographer_url'],
                    'unsplash_url': result['unsplash_url'],
                },
            }
            db.update_article(slug, updates)
            logger.info(f"  -> Updated with image by {result['photographer_name']}")
            updated += 1
        else:
            logger.warning(f"  -> No image found for: {title}")

        # Rate limit: wait between requests (skip after last)
        if i < len(articles) - 1:
            time.sleep(1.5)

    logger.info(f"Backfill complete: {updated}/{len(articles)} articles updated")
    return updated


if __name__ == '__main__':
    count = backfill_images()
    print(f"\nDone. Updated {count} article(s) with images.")
