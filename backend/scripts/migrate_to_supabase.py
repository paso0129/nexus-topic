#!/usr/bin/env python3
"""
Supabase Migration Script

Migrates existing JSON articles to Supabase database.
Supports dry-run, verify, and rollback modes.

Usage:
  # Dry run (no changes)
  python migrate_to_supabase.py --dry-run --articles-dir ../frontend/public/articles

  # Actual migration
  python migrate_to_supabase.py --articles-dir ../frontend/public/articles

  # Verify migration
  python migrate_to_supabase.py --verify --articles-dir ../frontend/public/articles

  # Rollback (delete all articles)
  python migrate_to_supabase.py --rollback
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from database import get_db_client, is_supabase_enabled

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics"""

    def __init__(self):
        self.total = 0
        self.successful = 0
        self.failed = 0
        self.skipped = 0
        self.errors: List[Dict] = []

    def record_success(self, slug: str):
        self.successful += 1
        logger.info(f"✓ Migrated: {slug}")

    def record_failure(self, slug: str, error: str):
        self.failed += 1
        self.errors.append({'slug': slug, 'error': error})
        logger.error(f"✗ Failed: {slug} - {error}")

    def record_skip(self, slug: str, reason: str):
        self.skipped += 1
        logger.warning(f"⊘ Skipped: {slug} - {reason}")

    def print_summary(self):
        logger.info("\n" + "=" * 80)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total articles processed: {self.total}")
        logger.info(f"Successfully migrated: {self.successful}")
        logger.info(f"Failed: {self.failed}")
        logger.info(f"Skipped: {self.skipped}")

        if self.errors:
            logger.info("\nErrors:")
            for error in self.errors:
                logger.info(f"  - {error['slug']}: {error['error']}")

    def save_log(self, log_path: str):
        """Save migration log to file"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'total': self.total,
            'successful': self.successful,
            'failed': self.failed,
            'skipped': self.skipped,
            'errors': self.errors
        }

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)

        logger.info(f"\nMigration log saved to: {log_path}")


def load_json_articles(articles_dir: str) -> List[Dict]:
    """
    Load all articles from JSON files.

    Args:
        articles_dir: Directory containing article JSON files

    Returns:
        List of article dictionaries
    """
    articles_path = Path(articles_dir)

    if not articles_path.exists():
        logger.error(f"Articles directory not found: {articles_dir}")
        return []

    articles = []

    for json_file in articles_path.glob('*.json'):
        # Skip index file
        if json_file.name == 'index.json':
            continue

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                article = json.load(f)
                articles.append(article)
        except Exception as e:
            logger.error(f"Error loading {json_file}: {str(e)}")
            continue

    logger.info(f"Loaded {len(articles)} articles from {articles_dir}")
    return articles


def migrate_article(article: Dict, db, dry_run: bool = False) -> bool:
    """
    Migrate a single article to Supabase.

    Args:
        article: Article dictionary
        db: Database client instance
        dry_run: If True, don't actually insert

    Returns:
        True if successful, False otherwise
    """
    slug = article.get('slug', '')

    if not slug:
        logger.error("Article missing slug")
        return False

    # Check if already exists
    if db.check_slug_exists(slug):
        logger.warning(f"Article already exists: {slug}")
        return False

    if dry_run:
        logger.info(f"[DRY RUN] Would migrate: {slug}")
        return True

    # Extract source data
    source_data = article.get('source_data', {})

    # Create article in database
    result = db.create_article(
        slug=slug,
        title=article.get('title', ''),
        content=article.get('content', ''),
        meta_description=article.get('meta_description', ''),
        keywords=article.get('keywords', []),
        reading_time=article.get('reading_time', 5),
        word_count=article.get('word_count', 0),
        topic=article.get('topic', ''),
        published=article.get('published', True),
        featured_image=article.get('featured_image', ''),
        author=article.get('author', {
            'name': 'AI Content Generator',
            'bio': 'Automated content powered by Claude AI'
        }),
        source_data=source_data if source_data else None
    )

    return result is not None


def verify_migration(articles: List[Dict], db) -> Dict[str, int]:
    """
    Verify that all articles were migrated successfully.

    Args:
        articles: List of article dictionaries from JSON
        db: Database client instance

    Returns:
        Dictionary with verification results
    """
    results = {
        'total': len(articles),
        'found': 0,
        'missing': 0,
        'missing_slugs': []
    }

    logger.info("\nVerifying migration...")

    for article in articles:
        slug = article.get('slug', '')

        if not slug:
            continue

        if db.check_slug_exists(slug):
            results['found'] += 1
            logger.info(f"✓ Found: {slug}")
        else:
            results['missing'] += 1
            results['missing_slugs'].append(slug)
            logger.error(f"✗ Missing: {slug}")

    return results


def rollback_migration(db) -> int:
    """
    Delete all articles from database.

    Args:
        db: Database client instance

    Returns:
        Number of articles deleted
    """
    logger.warning("\n" + "=" * 80)
    logger.warning("ROLLBACK MODE - DELETING ALL ARTICLES")
    logger.warning("=" * 80)

    confirmation = input("\nAre you sure you want to delete ALL articles? Type 'yes' to confirm: ")

    if confirmation.lower() != 'yes':
        logger.info("Rollback cancelled")
        return 0

    # Get all articles
    articles = db.list_articles(limit=1000, published_only=False)
    count = len(articles)

    logger.info(f"\nDeleting {count} articles...")

    deleted = 0
    for article in articles:
        slug = article.get('slug', '')
        if db.delete_article(slug):
            deleted += 1
            logger.info(f"✓ Deleted: {slug}")
        else:
            logger.error(f"✗ Failed to delete: {slug}")

    logger.info(f"\nDeleted {deleted}/{count} articles")
    return deleted


def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(
        description='Migrate JSON articles to Supabase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run
  python migrate_to_supabase.py --dry-run --articles-dir ../frontend/public/articles

  # Actual migration
  python migrate_to_supabase.py --articles-dir ../frontend/public/articles

  # Verify migration
  python migrate_to_supabase.py --verify --articles-dir ../frontend/public/articles

  # Rollback (delete all)
  python migrate_to_supabase.py --rollback
        """
    )

    parser.add_argument(
        '--articles-dir',
        type=str,
        default='../frontend/public/articles',
        help='Directory containing article JSON files'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate migration without making changes'
    )

    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify that all articles were migrated'
    )

    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Delete all articles from database'
    )

    parser.add_argument(
        '--log-file',
        type=str,
        default=f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
        help='Path to save migration log'
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SUPABASE MIGRATION SCRIPT")
    logger.info("=" * 80)

    # Check Supabase is enabled
    if not is_supabase_enabled():
        logger.error("Supabase is not enabled. Set USE_SUPABASE=true in .env")
        sys.exit(1)

    # Initialize database client
    try:
        db = get_db_client()

        if not db.test_connection():
            logger.error("Database connection failed")
            sys.exit(1)

        logger.info("✓ Database connection successful\n")

    except Exception as e:
        logger.error(f"Failed to initialize database client: {str(e)}")
        sys.exit(1)

    # Rollback mode
    if args.rollback:
        deleted = rollback_migration(db)
        logger.info(f"\nRollback complete. {deleted} articles deleted.")
        return

    # Load articles
    articles = load_json_articles(args.articles_dir)

    if not articles:
        logger.error("No articles found to migrate")
        sys.exit(1)

    # Verify mode
    if args.verify:
        results = verify_migration(articles, db)

        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total articles: {results['total']}")
        logger.info(f"Found in database: {results['found']}")
        logger.info(f"Missing from database: {results['missing']}")

        if results['missing_slugs']:
            logger.info("\nMissing articles:")
            for slug in results['missing_slugs']:
                logger.info(f"  - {slug}")

        if results['missing'] == 0:
            logger.info("\n✓ All articles verified successfully!")
            sys.exit(0)
        else:
            logger.error(f"\n✗ {results['missing']} articles missing from database")
            sys.exit(1)

    # Migration mode
    stats = MigrationStats()
    stats.total = len(articles)

    if args.dry_run:
        logger.info("\n[DRY RUN MODE - No changes will be made]\n")

    logger.info(f"Starting migration of {stats.total} articles...\n")

    for i, article in enumerate(articles, 1):
        slug = article.get('slug', f'article-{i}')
        logger.info(f"[{i}/{stats.total}] Processing: {slug}")

        try:
            if migrate_article(article, db, dry_run=args.dry_run):
                stats.record_success(slug)
            else:
                if db.check_slug_exists(slug):
                    stats.record_skip(slug, "Already exists")
                else:
                    stats.record_failure(slug, "Unknown error")

        except Exception as e:
            stats.record_failure(slug, str(e))

    # Print summary
    stats.print_summary()

    # Save log
    if not args.dry_run:
        stats.save_log(args.log_file)

    # Exit with appropriate code
    if stats.failed > 0:
        sys.exit(1)
    else:
        logger.info("\n✓ Migration completed successfully!")
        sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\nMigration interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
