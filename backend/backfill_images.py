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

from scripts.database import DatabaseClient
from scripts.fetch_images import generate_gemini_image


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

        # Generate image with Gemini
        image_url = generate_gemini_image(article)

        if image_url:
            # Update article in DB
            result = db.update_article(slug, {
                'featured_image': image_url,
                'image_attribution': {
                    'source': 'gemini',
                    'model': 'gemini-2.5-flash-image',
                },
            })
            if result:
                success += 1
                logger.info(f"  -> Updated: {image_url}")
            else:
                failed += 1
                logger.error(f"  -> DB update failed for {slug}")
        else:
            failed += 1
            logger.warning(f"  -> Image generation failed")

        # Rate limit: wait between requests
        if i < len(articles) - 1:
            time.sleep(3)

    logger.info(f"\nBackfill complete: {success} updated, {failed} failed out of {len(articles)} articles")


if __name__ == '__main__':
    main()
