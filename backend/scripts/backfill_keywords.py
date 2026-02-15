"""
Backfill keywords for existing articles by re-extracting from content.

Removes stop words and generates meaningful keywords only.

Usage:
  python scripts/backfill_keywords.py [--dry-run]
"""

import os
import re
import logging
import argparse

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

supabase = create_client(
    os.environ['SUPABASE_URL'],
    os.environ['SUPABASE_SERVICE_KEY']
)

STOP_WORDS = {
    'this', 'that', 'with', 'from', 'which', 'their', 'there', 'these',
    'those', 'then', 'than', 'them', 'they', 'been', 'being', 'were',
    'have', 'having', 'does', 'doing', 'done', 'will', 'would', 'could',
    'should', 'might', 'must', 'shall', 'about', 'above', 'after', 'again',
    'also', 'another', 'back', 'because', 'before', 'between', 'both',
    'came', 'come', 'each', 'even', 'every', 'find', 'first', 'found',
    'give', 'going', 'gone', 'good', 'great', 'help', 'here', 'high',
    'however', 'into', 'just', 'keep', 'know', 'known', 'last', 'left',
    'like', 'line', 'long', 'look', 'made', 'make', 'many', 'more',
    'most', 'much', 'need', 'never', 'next', 'only', 'open', 'other',
    'over', 'part', 'point', 'really', 'right', 'same', 'seem', 'show',
    'side', 'since', 'small', 'some', 'something', 'still', 'such',
    'sure', 'take', 'tell', 'thing', 'think', 'through', 'time', 'turn',
    'under', 'upon', 'used', 'using', 'very', 'want', 'well', 'what',
    'when', 'where', 'while', 'work', 'world', 'year', 'your',
    'able', 'allow', 'around', 'away', 'become', 'best', 'better',
    'call', 'case', 'change', 'clear', 'close', 'consider', 'create',
    'current', 'different', 'down', 'early', 'else', 'enough', 'ever',
    'example', 'face', 'fact', 'feel', 'form', 'full', 'further',
    'general', 'gets', 'given', 'goes', 'hand', 'hard', 'head',
    'home', 'house', 'human', 'important', 'include', 'issue', 'itself',
    'kind', 'large', 'late', 'lead', 'least', 'less', 'level', 'life',
    'likely', 'live', 'local', 'makes', 'matter', 'mean', 'means',
    'move', 'name', 'near', 'number', 'offer', 'often', 'order',
    'place', 'plan', 'play', 'possible', 'power', 'problem', 'provide',
    'public', 'question', 'quite', 'read', 'real', 'reason', 'result',
    'room', 'said', 'says', 'second', 'sense', 'service', 'several',
    'simply', 'sort', 'start', 'state', 'story', 'system', 'term',
    'things', 'thought', 'today', 'together', 'took', 'true', 'until',
    'ways', 'whole', 'word', 'words', 'wrote', 'years',
    'also', 'already', 'always', 'among', 'based', 'bring', 'built',
    'called', 'comes', 'common', 'complete', 'control', 'design',
    'developed', 'doesn', 'during', 'either', 'enable', 'entire',
    'exactly', 'feature', 'features', 'following', 'ground', 'group',
    'growing', 'itself', 'major', 'making', 'model', 'models',
    'modern', 'natural', 'needs', 'original', 'particularly',
    'people', 'potential', 'rather', 'remain', 'running', 'single',
    'specific', 'support', 'taken', 'three', 'toward', 'towards',
    'type', 'types', 'understanding', 'without',
    'adsbygoogle', 'window', 'push', 'pagead', 'script', 'class',
    'style', 'href', 'http', 'https', 'data', 'content', 'users',
}


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """Extract meaningful keywords from content, filtering stop words."""
    clean_text = re.sub(r'<[^>]+>', '', content)
    words = re.findall(r'\b[a-z]{4,}\b', clean_text.lower())

    word_freq = {}
    for word in words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_words[:max_keywords]]


def has_stop_words(keywords: list) -> bool:
    """Check if any keyword is a stop word."""
    return any(kw.lower() in STOP_WORDS for kw in keywords)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Show changes without updating')
    args = parser.parse_args()

    logger.info("Fetching all articles...")
    articles = supabase.table('articles').select('id, slug, title, content, keywords').execute().data or []
    logger.info(f"Found {len(articles)} articles")

    updated = 0
    skipped = 0

    for article in articles:
        old_kw = article.get('keywords') or []

        if not has_stop_words(old_kw) and len(old_kw) > 0:
            skipped += 1
            continue

        new_kw = extract_keywords(article['content'])

        logger.info(f"  {article['slug']}")
        logger.info(f"    OLD: {old_kw[:5]}")
        logger.info(f"    NEW: {new_kw[:5]}")

        if not args.dry_run:
            try:
                supabase.table('articles').update({'keywords': new_kw}).eq('id', article['id']).execute()
                updated += 1
            except Exception as e:
                logger.warning(f"    Failed to update: {e}")
        else:
            updated += 1

    logger.info(f"\nDone! Updated: {updated}, Skipped (already clean): {skipped}")
    if args.dry_run:
        logger.info("(dry run - no changes made)")


if __name__ == '__main__':
    main()
