"""
Migrate article slugs from romanized Korean to sequential numeric IDs.

Example: koseupi-5500-dolpa-2026nyeon-3weol-jinjja-wigineun-ddaro-issda → 1042

Step 1: Add old_slug column if not exists (via RPC/raw SQL)
Step 2: Copy current slug to old_slug
Step 3: Update slug to numeric ID

Usage: python -m scripts.migrate_slugs
"""
import os
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

START_ID = 1001


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    # Step 1: Add old_slug column if not exists
    try:
        supabase.rpc('exec_sql', {
            'query': "ALTER TABLE articles ADD COLUMN IF NOT EXISTS old_slug TEXT;"
        }).execute()
        logger.info("old_slug 컬럼 확인/추가 완료")
    except Exception as e:
        # If RPC doesn't exist, try direct approach — column may already exist
        logger.warning(f"RPC exec_sql 실패 (컬럼이 이미 있을 수 있음): {e}")

    # Fetch ALL articles ordered by creation date (oldest first for stable numbering)
    result = supabase.table('articles').select(
        'id, slug, title, created_at'
    ).order('created_at', desc=False).execute()

    articles = result.data or []
    logger.info(f"Total articles: {len(articles)}")

    # Print redirect mapping for frontend hardcoding
    redirect_map = {}
    migrated = 0
    skipped = 0

    for i, a in enumerate(articles):
        new_slug = str(START_ID + i)
        old_slug = a['slug']

        # Already migrated
        if old_slug == new_slug:
            skipped += 1
            continue

        if old_slug.isdigit():
            logger.warning(f"  Already numeric slug {old_slug}, skipping: {a['title'][:40]}")
            skipped += 1
            continue

        redirect_map[old_slug] = new_slug

        try:
            supabase.table('articles').update({
                'slug': new_slug,
                'old_slug': old_slug,
            }).eq('id', a['id']).execute()
            logger.info(f"  {old_slug} → {new_slug} ({a['title'][:40]})")
            migrated += 1
        except Exception as e:
            # If old_slug column doesn't exist, update without it
            logger.warning(f"  old_slug 컬럼 없음, slug만 변경: {e}")
            supabase.table('articles').update({
                'slug': new_slug,
            }).eq('id', a['id']).execute()
            logger.info(f"  {old_slug} → {new_slug} ({a['title'][:40]})")
            migrated += 1

    logger.info(f"\n결과: {migrated}개 slug 변경, {skipped}개 스킵")

    # Print redirect map for frontend middleware
    if redirect_map:
        logger.info("\n=== REDIRECT MAP (프론트엔드 middleware에 복사) ===")
        logger.info("const SLUG_REDIRECTS: Record<string, string> = {")
        for old, new in redirect_map.items():
            logger.info(f"  '{old}': '{new}',")
        logger.info("};")


if __name__ == '__main__':
    main()
