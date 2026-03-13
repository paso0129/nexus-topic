"""
Migrate article slugs from romanized Korean to sequential numeric IDs.

Example: koseupi-5500-dolpa-2026nyeon-3weol-jinjja-wigineun-ddaro-issda → 1042

Assigns sequential IDs based on created_at order (oldest first).
Old slugs are stored in source_data.old_slug for redirect mapping.

Usage: python -m scripts.migrate_slugs
"""
import os
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Starting ID — set high enough to avoid collisions
START_ID = 1001


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    # Fetch ALL articles ordered by creation date (oldest first for stable numbering)
    result = supabase.table('articles').select(
        'id, slug, title, source_data, created_at'
    ).order('created_at', desc=False).execute()

    articles = result.data or []
    logger.info(f"Total articles: {len(articles)}")

    migrated = 0
    skipped = 0

    for i, a in enumerate(articles):
        new_slug = str(START_ID + i)
        old_slug = a['slug']

        # Already migrated
        if old_slug == new_slug:
            skipped += 1
            continue

        # Already a numeric slug (different number — shouldn't happen)
        if old_slug.isdigit():
            logger.warning(f"  Already numeric slug {old_slug}, skipping: {a['title'][:40]}")
            skipped += 1
            continue

        # Store old slug in source_data for redirect mapping
        source_data = a.get('source_data') or {}
        source_data['old_slug'] = old_slug

        supabase.table('articles').update({
            'slug': new_slug,
            'source_data': source_data,
        }).eq('id', a['id']).execute()

        logger.info(f"  {old_slug} → {new_slug} ({a['title'][:40]})")
        migrated += 1

    logger.info(f"\n결과: {migrated}개 slug 변경, {skipped}개 스킵")


if __name__ == '__main__':
    main()
