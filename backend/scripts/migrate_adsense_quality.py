"""
AdSense Quality Migration Script

Performs three operations on all published articles:
1. Reassign author from fake personas to "NexusTopic 편집팀"
2. Append AI disclosure to article content (if missing)
3. Audit and flag short articles (< 800 words) for review

Usage:
  python -m scripts.migrate_adsense_quality --dry-run    # Preview changes
  python -m scripts.migrate_adsense_quality               # Apply changes
  python -m scripts.migrate_adsense_quality --unpublish   # Also unpublish flagged articles
"""

import os
import re
import argparse
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

EDITORIAL_AUTHOR = {
    'name': 'NexusTopic 편집팀',
    'bio': 'AI를 활용하여 트렌딩 이슈를 데이터 기반으로 분석하고, 편집팀이 팩트체크와 최종 검토를 수행합니다.',
}

AI_DISCLOSURE_HTML = (
    '<p class="ai-disclosure">이 기사는 AI 분석을 기반으로 작성되었으며, '
    'NexusTopic 편집팀이 검토했습니다.</p>'
)

FAKE_AUTHOR_NAMES = {'송민재', '임새봄', '정상열', '안다혜', '강희주', '변현선'}

# Remap removed categories to active ones
CATEGORY_REMAP = {
    '정치': '경제',
    '사회': '경제',
    '글로벌 사회': '글로벌 경제',
}

MIN_WORD_COUNT = 800  # Articles below this are flagged


def count_words(html_content: str) -> int:
    """Count words (어절) in HTML content."""
    text = re.sub(r'<[^>]+>', '', html_content)
    return len(text.split())


def has_ai_disclosure(content: str) -> bool:
    """Check if content already contains AI disclosure."""
    return 'ai-disclosure' in content


def count_source_links(content: str) -> int:
    """Count external links in content."""
    return len(re.findall(r'<a\s+[^>]*href=["\']https?://', content))


def main():
    parser = argparse.ArgumentParser(description='AdSense quality migration')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--unpublish', action='store_true', help='Unpublish flagged short articles')
    args = parser.parse_args()

    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    # Fetch all published articles
    result = supabase.table('articles').select(
        'id, slug, title, content, topic, author, word_count, published'
    ).eq('published', True).execute()

    articles = result.data or []
    logger.info(f"Total published articles: {len(articles)}")

    # Counters
    author_updated = 0
    disclosure_added = 0
    category_remapped = 0
    flagged_short = []
    flagged_no_sources = []

    for a in articles:
        slug = a['slug']
        content = a.get('content', '')
        updates = {}

        # --- 0. Category remap (remove legacy categories) ---
        current_topic = a.get('topic', '')
        if current_topic in CATEGORY_REMAP:
            updates['topic'] = CATEGORY_REMAP[current_topic]
            category_remapped += 1

        # --- 1. Author reassignment ---
        current_author = a.get('author', {}) or {}
        current_name = current_author.get('name', '')
        if current_name in FAKE_AUTHOR_NAMES or current_name != EDITORIAL_AUTHOR['name']:
            updates['author'] = EDITORIAL_AUTHOR
            author_updated += 1

        # --- 2. AI disclosure ---
        if content and not has_ai_disclosure(content):
            updated_content = content.rstrip() + '\n' + AI_DISCLOSURE_HTML
            updates['content'] = updated_content
            disclosure_added += 1

        # --- 3. Word count audit ---
        actual_wc = count_words(content) if content else 0
        source_count = count_source_links(content) if content else 0

        if actual_wc < MIN_WORD_COUNT:
            flagged_short.append({
                'slug': slug,
                'title': a.get('title', '')[:50],
                'word_count': actual_wc,
                'sources': source_count,
                'topic': a.get('topic', ''),
            })
            if args.unpublish:
                updates['published'] = False

        if source_count < 2:
            flagged_no_sources.append({
                'slug': slug,
                'title': a.get('title', '')[:50],
                'word_count': actual_wc,
                'sources': source_count,
            })

        # --- Apply updates ---
        if updates:
            if args.dry_run:
                changes = ', '.join(updates.keys())
                logger.info(f"  [DRY-RUN] {slug}: would update {changes}")
            else:
                supabase.table('articles').update(updates).eq('id', a['id']).execute()

    # --- Report ---
    logger.info(f"\n{'=' * 60}")
    logger.info(f"MIGRATION REPORT")
    logger.info(f"{'=' * 60}")
    logger.info(f"Authors reassigned:    {author_updated}")
    logger.info(f"Categories remapped:   {category_remapped}")
    logger.info(f"AI disclosures added:  {disclosure_added}")
    logger.info(f"Flagged short (<{MIN_WORD_COUNT}w): {len(flagged_short)}")
    logger.info(f"Flagged no sources (<2): {len(flagged_no_sources)}")

    if flagged_short:
        logger.info(f"\n--- Short articles ({len(flagged_short)}) ---")
        for f in sorted(flagged_short, key=lambda x: x['word_count']):
            status = "UNPUBLISHED" if args.unpublish and not args.dry_run else "FLAGGED"
            logger.info(
                f"  [{status}] {f['slug']:>5} | {f['word_count']:>4}w | "
                f"{f['sources']} sources | [{f['topic']}] {f['title']}"
            )

    if flagged_no_sources:
        logger.info(f"\n--- Low-source articles ({len(flagged_no_sources)}) ---")
        for f in sorted(flagged_no_sources, key=lambda x: x['sources']):
            logger.info(
                f"  {f['slug']:>5} | {f['word_count']:>4}w | "
                f"{f['sources']} sources | {f['title']}"
            )

    if args.dry_run:
        logger.info(f"\n⚠️  DRY-RUN mode — no changes applied. Remove --dry-run to execute.")
    else:
        logger.info(f"\n✅ Migration complete.")


if __name__ == '__main__':
    main()
