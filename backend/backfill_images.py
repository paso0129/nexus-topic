"""
Backfill missing article images using Gemini AI (Nano Banana).
Finds articles without featured_image and generates + uploads them.
"""

import os
import sys
import time
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import requests as http_requests

from scripts.database import DatabaseClient
from scripts.fetch_images import generate_gemini_image, _build_search_query, fetch_unsplash_image


def _revalidate_slug(slug: str):
    """Revalidate ISR cache for a specific article slug."""
    revalidation_secret = os.getenv('REVALIDATION_SECRET', '')
    if not revalidation_secret:
        return
    try:
        resp = http_requests.post(
            "https://www.nexustopic.com/api/revalidate",
            headers={
                "Authorization": f"Bearer {revalidation_secret}",
                "Content-Type": "application/json",
            },
            json={"paths": [f"/article/{slug}"]},
            timeout=10,
        )
        logger.info(f"  Revalidated /article/{slug}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"  Revalidation failed for {slug}: {e}")


def main():
    db = DatabaseClient()

    # Find articles without images
    articles = db.list_articles_without_images()
    if not articles:
        logger.info("All articles already have images!")
        return

    logger.info(f"Found {len(articles)} articles without images")

    success = 0
    failed = 0

    for i, article in enumerate(articles):
        title = article.get('title', '')[:60]
        slug = article.get('slug', '')
        logger.info(f"\n[{i+1}/{len(articles)}] {title}...")

        image_url = None
        attribution = None

        # 1) Try Gemini AI image generation
        image_url = generate_gemini_image(article)
        if image_url:
            attribution = {
                'source': 'gemini',
                'model': 'gemini-2.5-flash-image',
            }
        else:
            # 2) Fallback to Unsplash
            logger.info(f"  Gemini failed, trying Unsplash fallback...")
            query = _build_search_query(article)
            logger.info(f"  Unsplash query: '{query}'")
            unsplash_result = fetch_unsplash_image(query)
            if unsplash_result:
                image_url = unsplash_result['url']
                attribution = {
                    'source': 'unsplash',
                    'photographer_name': unsplash_result['photographer_name'],
                    'photographer_url': unsplash_result['photographer_url'],
                    'unsplash_url': unsplash_result['unsplash_url'],
                }
                logger.info(f"  -> Unsplash image by {unsplash_result['photographer_name']}")

        if image_url:
            # Update article in DB
            result = db.update_article(slug, {
                'featured_image': image_url,
                'image_attribution': attribution,
            })
            if result:
                success += 1
                logger.info(f"  -> Updated: {image_url}")
                _revalidate_slug(slug)
            else:
                failed += 1
                logger.error(f"  -> DB update failed for {slug}")
        else:
            failed += 1
            logger.warning(f"  -> All image sources failed")

        # Rate limit: wait between requests
        if i < len(articles) - 1:
            time.sleep(3)

    logger.info(f"\nBackfill complete: {success} updated, {failed} failed out of {len(articles)} articles")


if __name__ == '__main__':
    main()
