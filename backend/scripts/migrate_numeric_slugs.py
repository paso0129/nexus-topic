"""
Migrate numeric article slugs back to SEO-friendly Korean UTF-8 slugs.

Reverses the 2026-03 numeric migration. Reads each article's title and
generates a keyword-rich Korean slug. Preserves old numeric slug in
`old_slug` so middleware can 301 redirect legacy URLs.

Usage:
    python -m scripts.migrate_numeric_slugs --dry-run
    python -m scripts.migrate_numeric_slugs --apply

Environment:
    SUPABASE_URL, SUPABASE_SERVICE_KEY

Safety:
    - Dry-run by default. Only writes with --apply.
    - Only touches articles with purely numeric slugs.
    - Resolves collisions with -2/-3 suffix.
    - Writes a redirect_map.json for audit.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List

from supabase import create_client

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.save_article import slugify_korean  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def fetch_numeric_slug_articles(supabase) -> List[Dict]:
    """Fetch all published articles whose slug is purely numeric."""
    result = supabase.table('articles').select(
        'id, slug, title, old_slug, published'
    ).eq('published', True).order('created_at', desc=False).execute()

    articles = result.data or []
    return [a for a in articles if a.get('slug', '').isdigit()]


def fetch_all_slugs(supabase) -> set:
    """Fetch every existing slug and old_slug to detect collisions."""
    result = supabase.table('articles').select('slug, old_slug').execute()
    taken = set()
    for row in (result.data or []):
        if row.get('slug'):
            taken.add(row['slug'])
        if row.get('old_slug'):
            taken.add(row['old_slug'])
    return taken


def resolve_collision(base: str, taken: set) -> str:
    """Pick a non-colliding slug by appending -2, -3, ... suffix."""
    if base not in taken:
        return base
    for suffix in range(2, 100):
        candidate = f"{base}-{suffix}"
        if candidate not in taken:
            return candidate
    raise RuntimeError(f"Cannot resolve collision for base {base!r}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to database (default: dry-run)')
    parser.add_argument('--limit', type=int, default=0,
                        help='Process at most N articles (0 = all)')
    parser.add_argument('--output', default='redirect_map.json',
                        help='Path to write redirect map JSON')
    args = parser.parse_args()

    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    articles = fetch_numeric_slug_articles(supabase)
    logger.info(f"Numeric-slug articles found: {len(articles)}")

    if args.limit > 0:
        articles = articles[:args.limit]
        logger.info(f"Limited to first {args.limit}")

    if not articles:
        logger.info("No numeric slugs to migrate. Done.")
        return

    taken = fetch_all_slugs(supabase)
    logger.info(f"Existing slug/old_slug entries: {len(taken)}")

    migrations: List[Dict[str, str]] = []
    for article in articles:
        numeric_slug = article['slug']
        title = article.get('title') or ''
        base = slugify_korean(title)
        if base == 'article':
            logger.warning(f"  Skipping {numeric_slug}: title produced no slug ({title[:40]!r})")
            continue
        new_slug = resolve_collision(base, taken)
        taken.add(new_slug)
        migrations.append({
            'id': article['id'],
            'old': numeric_slug,
            'new': new_slug,
            'title': title[:60],
        })

    logger.info(f"Planned migrations: {len(migrations)}")
    for m in migrations[:10]:
        logger.info(f"  {m['old']} → {m['new']}  ({m['title']})")
    if len(migrations) > 10:
        logger.info(f"  ... and {len(migrations) - 10} more")

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(
            {m['old']: m['new'] for m in migrations},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    logger.info(f"Redirect map written to {output_path.resolve()}")

    if not args.apply:
        logger.info("\nDry-run complete. Re-run with --apply to commit changes.")
        return

    logger.info("\n=== APPLYING CHANGES ===")
    succeeded = 0
    failed = 0
    for m in migrations:
        try:
            supabase.table('articles').update({
                'slug': m['new'],
                'old_slug': m['old'],
            }).eq('id', m['id']).execute()
            succeeded += 1
        except Exception as e:
            logger.error(f"  FAIL {m['old']} → {m['new']}: {e}")
            failed += 1

    logger.info(f"\nResult: {succeeded} migrated, {failed} failed")


if __name__ == '__main__':
    main()
