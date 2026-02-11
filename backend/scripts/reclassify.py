"""
Article Category Classifier

Classifies articles into predefined categories using Claude Haiku.
Can be used inline during article generation or as a standalone CLI
to reclassify existing articles in the database.

Usage:
    python -m scripts.reclassify
"""
import os
import logging
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic

logger = logging.getLogger(__name__)

VALID_CATEGORIES = [
    'AI', 'BIZ & IT', 'CARS', 'CULTURE', 'GAMING', 'HEALTH',
    'POLICY', 'SCIENCE', 'SECURITY', 'SPACE', 'TECH',
]


def classify_article(client: Anthropic, article: Dict) -> str:
    """
    Classify a single article into a category using Claude Haiku.

    Args:
        client: Anthropic client instance
        article: Article dict with 'title' and 'content' keys

    Returns:
        Category string from VALID_CATEGORIES
    """
    title = article.get('title', '')
    content = article.get('content', '')[:1000]
    fallback = article.get('topic', 'TECH')

    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=20,
            messages=[{
                'role': 'user',
                'content': (
                    f"Classify this article into exactly ONE category from this list: "
                    f"{VALID_CATEGORIES}\n\n"
                    f"Title: {title}\n"
                    f"Content preview: {content}\n\n"
                    f"Reply with ONLY the category name, nothing else."
                ),
            }],
        )
        category = resp.content[0].text.strip().upper()
        if 'BIZ' in category:
            category = 'BIZ & IT'
        if category not in VALID_CATEGORIES:
            logger.warning(f"Invalid category '{category}' for '{title}', keeping '{fallback}'")
            return fallback
        return category
    except Exception as e:
        logger.warning(f"Classification failed for '{title}': {e}")
        return fallback


def classify_articles(articles: List[Dict]) -> List[Dict]:
    """
    Verify and correct categories for a list of articles (in-memory).
    Used in the generation pipeline before saving.

    Args:
        articles: List of article dicts from generate_multiple_articles

    Returns:
        Same list with corrected 'topic' fields
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping classification")
        return articles

    client = Anthropic(api_key=api_key)
    corrected = 0

    for i, article in enumerate(articles):
        old_cat = article.get('topic', 'TECH')
        new_cat = classify_article(client, article)

        if new_cat != old_cat:
            logger.info(f"Category corrected: '{old_cat}' -> '{new_cat}' for '{article['title']}'")
            article['topic'] = new_cat
            corrected += 1
        else:
            logger.info(f"Category confirmed: '{new_cat}' for '{article['title']}'")

    logger.info(f"Classification done: {corrected}/{len(articles)} corrected")
    return articles


def reclassify_all():
    """Reclassify all existing articles in the database."""
    from scripts.database import get_db_client

    api_key = os.getenv('ANTHROPIC_API_KEY')
    client = Anthropic(api_key=api_key)
    db = get_db_client()
    articles = db.list_articles(limit=200, published_only=False)

    print(f"Total articles: {len(articles)}\n")
    changes = []

    for i, article in enumerate(articles):
        current = article.get('topic', 'TECH')
        slug = article.get('slug', '')
        new_cat = classify_article(client, article)

        changed = new_cat != current
        tag = 'CHANGED' if changed else 'ok'
        if changed:
            changes.append((slug, current, new_cat))
        print(f"[{i+1}/{len(articles)}] {tag:7s} {current:10s} -> {new_cat:10s}  {article['title']}")

    print(f"\n=== {len(changes)} categories to update ===")
    for slug, old, new in changes:
        db.update_article(slug, {'topic': new})
        print(f"  Updated: {old} -> {new}  ({slug})")

    print(f"\nDone. {len(changes)} articles reclassified.")
    return changes


if __name__ == '__main__':
    reclassify_all()
