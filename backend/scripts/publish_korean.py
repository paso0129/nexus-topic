"""
Publish all Korean articles (published=false → true).
Identifies Korean articles by checking if the title contains Korean characters.
"""
import os
import re
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

KOREAN_RE = re.compile(r'[\uac00-\ud7a3]')

def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    # Get all unpublished articles
    result = supabase.table('articles').select('id, slug, title').eq('published', False).execute()
    articles = result.data or []
    logger.info(f"Total unpublished articles: {len(articles)}")

    korean = [a for a in articles if KOREAN_RE.search(a['title'])]
    logger.info(f"Korean unpublished articles: {len(korean)}")

    if not korean:
        logger.info("No Korean articles to publish.")
        return

    for a in korean:
        logger.info(f"  Publishing: {a['slug']} — {a['title'][:50]}")

    ids = [a['id'] for a in korean]
    # Batch update
    for aid in ids:
        supabase.table('articles').update({'published': True}).eq('id', aid).execute()

    logger.info(f"Done. Published {len(ids)} Korean articles.")

if __name__ == '__main__':
    main()
