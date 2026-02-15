"""Fix articles with broken featured_image values (like '$undefined')."""

import os
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

    # Find ALL published articles and check for broken images
    result = db.client.table('articles') \
        .select('slug, title, topic, meta_description, featured_image') \
        .eq('published', True) \
        .execute()

    broken = []
    for a in result.data:
        img = a.get('featured_image', '')
        if not img or img == '$undefined' or img == 'undefined' or 'undefined' in str(img):
            broken.append(a)

    if not broken:
        logger.info("No broken images found!")
        return

    logger.info(f"Found {len(broken)} articles with broken images:")
    for a in broken:
        logger.info(f"  - {a['slug']} (image: {a.get('featured_image', 'null')})")

    success = 0
    for i, article in enumerate(broken):
        slug = article['slug']
        logger.info(f"\n[{i+1}/{len(broken)}] {article['title'][:60]}...")

        image_url = generate_gemini_image(article)
        if image_url:
            db.update_article(slug, {
                'featured_image': image_url,
                'image_attribution': {
                    'source': 'gemini',
                    'model': 'gemini-2.5-flash-image',
                },
            })
            success += 1
            logger.info(f"  -> Fixed: {image_url}")
        else:
            # Clear the broken value so frontend shows category thumbnail
            db.update_article(slug, {'featured_image': None})
            logger.info(f"  -> Cleared broken value, will show category thumbnail")

        if i < len(broken) - 1:
            time.sleep(3)

    logger.info(f"\nDone: {success} images generated, {len(broken) - success} cleared")


if __name__ == '__main__':
    main()
