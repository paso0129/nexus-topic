"""
Cleanup Gemini-generated Article Images

Finds articles with AI-generated images (source='gemini') and removes them.
Sets featured_image to null and image_attribution to empty so backfill_images
can replace them with Unsplash photos.

Usage:
    python -m scripts.cleanup_gemini_images
"""

import logging
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from scripts.database import get_db_client, is_supabase_enabled

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

STORAGE_BUCKET = 'article-images'


def extract_storage_path(image_url: str) -> str | None:
    """Extract the file path from a Supabase Storage public URL.

    URL format: https://xxx.supabase.co/storage/v1/object/public/article-images/SLUG.png
    Returns the path after the bucket name, e.g. 'SLUG.png'.
    """
    try:
        parsed = urlparse(image_url)
        prefix = f'/storage/v1/object/public/{STORAGE_BUCKET}/'
        idx = parsed.path.find(prefix)
        if idx == -1:
            return None
        return parsed.path[idx + len(prefix):]
    except Exception:
        return None


def cleanup_gemini_images() -> int:
    """Delete Gemini-generated images from storage and clear article references.

    Returns:
        Number of articles cleaned up.
    """
    if not is_supabase_enabled():
        logger.error("Supabase is not enabled. Set USE_SUPABASE=true")
        return 0

    db = get_db_client()

    # Find articles with gemini images
    result = db.client.table('articles') \
        .select('slug, featured_image, image_attribution') \
        .eq('image_attribution->>source', 'gemini') \
        .execute()

    articles = result.data
    if not articles:
        logger.info("No articles with Gemini images found.")
        return 0

    logger.info(f"Found {len(articles)} articles with Gemini images")
    cleaned = 0

    for article in articles:
        slug = article['slug']
        image_url = article.get('featured_image', '')

        # Delete from storage
        if image_url:
            storage_path = extract_storage_path(image_url)
            if storage_path:
                try:
                    db.client.storage.from_(STORAGE_BUCKET).remove([storage_path])
                    logger.info(f"Deleted storage file: {storage_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete storage file for {slug}: {e}")
            else:
                logger.warning(f"Could not parse storage path from URL for {slug}: {image_url}")

        # Clear article image fields
        db.update_article(slug, {
            'featured_image': None,
            'image_attribution': {},
        })
        logger.info(f"Cleared image fields for: {slug}")
        cleaned += 1

    logger.info(f"Cleanup complete: {cleaned}/{len(articles)} articles processed")
    return cleaned


if __name__ == '__main__':
    count = cleanup_gemini_images()
    logging.info(f"Done. Cleaned up {count} article(s).")
