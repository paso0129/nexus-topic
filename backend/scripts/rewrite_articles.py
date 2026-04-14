"""
Article Rewriter — Rewrites existing articles with human-like author personas.

Uses Gemini CLI (gemini-2.5-flash) to rewrite articles with:
- Author-specific voice (Alex Chen / Sarah Mitchell / Maya Rodriguez)
- 30-40 year old writing style
- Anti-AI patterns for Google compliance
"""

import logging
import os
import re
import subprocess
import shutil
import sys
import time

from dotenv import load_dotenv
load_dotenv()

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.database import get_db_client
from scripts.generate_content import (
    EDITORIAL_VOICE, _get_author_for_category,
    _generate_with_gemini_cli, _generate_with_gemini_api,
    calculate_reading_time, extract_keywords,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _build_rewrite_prompt(title: str, content: str, author_name: str, topic: str) -> str:
    """Build a prompt to rewrite an existing article with editorial voice."""
    return f"""REWRITE the following article with improved quality. Keep the same topic and key facts, but enhance analysis depth and source citations.

WRITING IDENTITY:
{EDITORIAL_VOICE}

REWRITING RULES:
- Keep the same core topic and key facts/statistics
- Completely change the sentence structure, phrasing, and flow
- Add deeper data-driven analysis with specific source citations
- NEVER use first person (나, 저, 내가, 필자, 우리) — use objective third-person only
- VARY sentence length: mix short punchy sentences with longer analytical ones
- NEVER use: "귀추가 주목된다", "지켜봐야 할 것이다", "결론적으로", "주목할 만하다", "패러다임", "게임체인저"
- Keep HTML format (h2, h3, p, ul, ol, strong, em, blockquote)
- Keep any existing <a href> links intact — preserve all external links
- Every statistic must include its source (organization name + year)
- Target length: 1500-2500 words (deeper than the original)
- Write a NEW headline (under 40 chars Korean) that's specific and data-driven
- Write a NEW meta description (under 160 chars)
- End with: <p class="ai-disclosure">이 기사는 AI 분석을 기반으로 작성되었으며, NexusTopic 편집팀이 검토했습니다.</p>

ORIGINAL TITLE: {title}
CATEGORY: {topic}

ORIGINAL CONTENT:
{content[:3000]}

FORMAT YOUR RESPONSE AS:
TITLE: [new headline]
META: [new meta description]
CONTENT:
[rewritten HTML content]
"""


def rewrite_article(article: dict, db) -> bool:
    """Rewrite a single article and update it in the database."""
    slug = article['slug']
    title = article.get('title', '')
    content = article.get('content', '')
    topic = article.get('topic', 'TECH')
    author_name = _get_author_for_category(topic)

    if not content or len(content) < 100:
        logger.warning(f"Skipping {slug}: content too short")
        return False

    prompt = _build_rewrite_prompt(title, content, author_name, topic)

    # Try Gemini CLI first (no quota limits)
    response_text = None
    try:
        response_text = _generate_with_gemini_cli(prompt, model="gemini-2.5-flash")
    except Exception as e:
        logger.warning(f"CLI failed for {slug}: {e}")

    # Fallback to API
    if not response_text:
        try:
            response_text = _generate_with_gemini_api(prompt)
            time.sleep(5)  # Rate limit
        except Exception as e:
            logger.error(f"API also failed for {slug}: {e}")
            return False

    # Parse response
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|META:)', response_text, re.IGNORECASE)
    meta_match = re.search(r'META:\s*(.+?)(?:\n|CONTENT:)', response_text, re.IGNORECASE)
    content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.IGNORECASE | re.DOTALL)

    if not content_match:
        logger.error(f"Failed to parse rewrite for {slug}")
        return False

    new_content = content_match.group(1).strip()
    new_title = title_match.group(1).strip() if title_match else title
    new_meta = meta_match.group(1).strip() if meta_match else ''

    word_count = len(re.sub(r'<[^>]+>', '', new_content).split())
    if word_count < 200:
        logger.warning(f"Rewrite too short ({word_count}w) for {slug}, skipping")
        return False

    updates = {
        'title': new_title,
        'content': new_content,
        'word_count': word_count,
        'reading_time': calculate_reading_time(new_content),
        'keywords': extract_keywords(new_content),
    }
    if new_meta:
        updates['meta_description'] = new_meta

    result = db.update_article(slug, updates)
    if result:
        logger.info(f"Rewritten [{topic}] by {author_name}: {new_title} ({word_count}w)")
        return True
    else:
        logger.error(f"DB update failed for {slug}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Rewrite existing articles with human personas')
    parser.add_argument('--limit', type=int, default=0, help='Max articles to rewrite (0=all)')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N articles')
    parser.add_argument('--category', type=str, default='', help='Only rewrite specific category')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be rewritten')
    args = parser.parse_args()

    db = get_db_client()

    # Get all articles ordered by oldest first
    query = db.client.table('articles').select(
        'slug, title, content, topic, created_at, word_count'
    ).order('created_at', desc=False)

    if args.category:
        query = query.eq('topic', args.category.upper())

    if args.limit > 0:
        query = query.limit(args.limit + args.offset)

    result = query.execute()
    articles = result.data[args.offset:]

    if args.limit > 0:
        articles = articles[:args.limit]

    print(f"\nArticles to rewrite: {len(articles)}")

    if args.dry_run:
        for a in articles:
            author = _get_author_for_category(a.get('topic', 'TECH'))
            print(f"  [{a['topic']:14s}] {author:18s} {a['title'][:55]}")
        return

    success = 0
    failed = 0
    for i, article in enumerate(articles):
        print(f"\n[{i+1}/{len(articles)}] Rewriting: {article['title'][:55]}...")
        try:
            if rewrite_article(article, db):
                success += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error rewriting {article['slug']}: {e}")
            failed += 1

        # Brief pause between articles
        if i < len(articles) - 1:
            time.sleep(2)

    print(f"\n=== Rewrite Complete ===")
    print(f"Success: {success}/{len(articles)}")
    print(f"Failed: {failed}/{len(articles)}")


if __name__ == '__main__':
    main()
