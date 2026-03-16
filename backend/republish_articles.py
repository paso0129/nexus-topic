"""
Republish unpublished articles that are in good shape.

Checks each unpublished article for:
- Has content (not empty)
- Is Korean (numeric slug = new format)
- Regenerates keywords if needed
- Fetches image if missing

Usage:
  cd backend && python republish_articles.py [--dry-run]
"""

import os
import sys
import re
import logging
import argparse

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Only report, do not modify')
    args = parser.parse_args()

    from scripts.database import DatabaseClient
    db = DatabaseClient()

    # Fetch ALL unpublished articles
    logger.info("Fetching unpublished articles...")
    result = db.client.table('articles') \
        .select('slug, title, content, keywords, featured_image, topic, published') \
        .eq('published', False) \
        .order('created_at', desc=True) \
        .limit(500) \
        .execute()

    articles = result.data
    logger.info(f"Found {len(articles)} unpublished articles")

    if not articles:
        logger.info("No unpublished articles found.")
        return

    publishable = []
    skipped = []

    for article in articles:
        slug = article.get('slug', '')
        title = article.get('title', '')
        content = article.get('content', '')
        keywords = article.get('keywords', [])
        image = article.get('featured_image', '')
        topic = article.get('topic', '')

        # Skip if no content
        if not content or len(content) < 200:
            skipped.append((slug, 'no content'))
            continue

        # Skip if content is not Korean (check for Korean characters)
        korean_chars = len(re.findall(r'[\uAC00-\uD7A3]', content))
        if korean_chars < 50:
            skipped.append((slug, f'not Korean ({korean_chars} chars)'))
            continue

        # Skip if no title
        if not title:
            skipped.append((slug, 'no title'))
            continue

        # Check if content is truncated (cut off mid-sentence/tag)
        content_truncated = False
        clean_content = content.strip()
        # Check for unclosed HTML tags
        open_tags = len(re.findall(r'<(h[23]|p|ul|ol|li|blockquote|strong|em)\b', clean_content))
        close_tags = len(re.findall(r'</(h[23]|p|ul|ol|li|blockquote|strong|em)>', clean_content))
        if open_tags > 0 and abs(open_tags - close_tags) > 3:
            content_truncated = True
        # Check if content ends abruptly (no closing tag, mid-sentence)
        if clean_content and not clean_content.rstrip().endswith('>') and not clean_content.rstrip().endswith('.') and not clean_content.rstrip().endswith('다'):
            content_truncated = True
        # Check word count (too short = likely truncated)
        word_count = len(re.sub(r'<[^>]+>', '', clean_content).split())
        if word_count < 300:
            content_truncated = True

        if content_truncated:
            skipped.append((slug, f'content truncated (words={word_count}, tags open={open_tags} close={close_tags})'))
            continue

        issues = []
        if not keywords or len(keywords) < 2:
            issues.append('needs keywords')
        if not image:
            issues.append('needs image')
        if not topic:
            issues.append('needs topic')

        # Check for bad keywords (1 char, truncated)
        if keywords:
            bad_kw = [k for k in keywords if len(k) < 2]
            if bad_kw:
                issues.append(f'bad keywords: {bad_kw}')

        publishable.append({
            'slug': slug,
            'title': title[:60],
            'issues': issues,
            'has_image': bool(image),
            'keyword_count': len(keywords or []),
            'topic': topic,
        })

    logger.info(f"\n{'='*60}")
    logger.info(f"Publishable: {len(publishable)}, Skipped: {len(skipped)}")
    logger.info(f"{'='*60}")

    for slug, reason in skipped:
        logger.info(f"  SKIP {slug}: {reason}")

    logger.info(f"\n--- Publishable articles ---")
    for art in publishable:
        issues_str = ', '.join(art['issues']) if art['issues'] else 'ready'
        logger.info(f"  {art['slug']}: {art['title']} [{art['topic']}] ({issues_str})")

    if args.dry_run:
        logger.info("\n[DRY RUN] No changes made.")
        return

    # Fix and publish
    success = 0
    failed = 0

    for art in publishable:
        slug = art['slug']
        update_data = {'published': True}

        try:
            # Regenerate keywords if needed
            if 'needs keywords' in art['issues'] or any('bad keywords' in i for i in art['issues']):
                try:
                    from regenerate_keywords import _generate_keywords_and_category
                    full_article = db.get_article(slug)
                    if full_article:
                        result = _generate_keywords_and_category(
                            full_article.get('title', ''),
                            full_article.get('content', '')
                        )
                        if result['keywords']:
                            update_data['keywords'] = result['keywords']
                            logger.info(f"  {slug}: new keywords = {result['keywords']}")
                        if result['category'] and not art['topic']:
                            update_data['topic'] = result['category']
                except Exception as e:
                    logger.warning(f"  {slug}: keyword regen failed: {e}")

            # Fetch image if missing
            if 'needs image' in art['issues']:
                try:
                    from scripts.fetch_images import fetch_image_for_article
                    full_article = db.get_article(slug)
                    if full_article:
                        image_url = fetch_image_for_article(full_article)
                        if image_url:
                            update_data['featured_image'] = image_url
                            logger.info(f"  {slug}: new image fetched")
                except Exception as e:
                    logger.warning(f"  {slug}: image fetch failed: {e}")

            # Publish
            db_result = db.update_article(slug, update_data)
            if db_result:
                success += 1
                logger.info(f"  ✅ Published: {slug}")
            else:
                failed += 1
                logger.error(f"  ❌ Failed to publish: {slug}")

        except Exception as e:
            failed += 1
            logger.error(f"  ❌ Error for {slug}: {e}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Done! Published: {success}, Failed: {failed}")

    # Revalidate all pages
    if success > 0:
        logger.info("Revalidating all pages...")
        import requests as http_requests
        secret = os.getenv('REVALIDATION_SECRET', '')
        if secret:
            try:
                resp = http_requests.post(
                    "https://www.nexustopic.com/api/revalidate",
                    headers={
                        "Authorization": f"Bearer {secret}",
                        "Content-Type": "application/json",
                    },
                    json={"all_articles": True},
                    timeout=10,
                )
                logger.info(f"Revalidated: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Revalidation failed: {e}")


if __name__ == '__main__':
    main()
