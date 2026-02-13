"""
Article Category Classifier

Classifies articles into predefined categories using:
- Primary: Gemini 3 Flash Preview via API (fast)
- Fallback: Gemini CLI (Google account auth)
"""
import os
import logging
import subprocess
import shutil
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

VALID_CATEGORIES = [
    'AI', 'BIZ & IT', 'CARS', 'CULTURE', 'GAMING', 'HEALTH',
    'POLICY', 'SCIENCE', 'SECURITY', 'SPACE', 'TECH',
]

_gemini_cli_path = shutil.which('gemini')


def _parse_category(text: str, fallback: str) -> str:
    """Parse and validate a category from LLM response."""
    category = text.strip().upper()
    if 'BIZ' in category:
        category = 'BIZ & IT'
    if category in VALID_CATEGORIES:
        return category
    return fallback


def classify_article(article: Dict) -> str:
    """
    Classify a single article into a category.
    Tries Gemini API first, falls back to Gemini CLI.
    """
    title = article.get('title', '')
    content = article.get('content', '')[:1000]
    fallback = article.get('topic', 'TECH')

    prompt = (
        f"Classify this article into exactly ONE category from this list: "
        f"{VALID_CATEGORIES}\n\n"
        f"Title: {title}\n"
        f"Content preview: {content}\n\n"
        f"Reply with ONLY the category name, nothing else."
    )

    # Try Gemini API (fast)
    if os.getenv('GOOGLE_API_KEY') and genai:
        try:
            genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
            model = genai.GenerativeModel('gemini-3-flash-preview')
            resp = model.generate_content(prompt)
            result = _parse_category(resp.text, fallback)
            if result != fallback:
                return result
            return result
        except Exception as e:
            logger.warning(f"Gemini API classification failed: {e}")

    # Fallback to Gemini CLI
    if _gemini_cli_path:
        try:
            result = subprocess.run(
                [_gemini_cli_path, '-m', 'gemini-2.5-flash', '-p', prompt],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split('\n')
                         if not l.startswith('Loaded cached') and not l.startswith('Hook registry')]
                return _parse_category('\n'.join(lines), fallback)
        except Exception as e:
            logger.warning(f"Gemini CLI classification failed: {e}")

    return fallback


def classify_articles(articles: List[Dict]) -> List[Dict]:
    """Verify and correct categories for a list of articles (in-memory)."""
    corrected = 0

    for i, article in enumerate(articles):
        old_cat = article.get('topic', 'TECH')
        new_cat = classify_article(article)

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

    db = get_db_client()
    articles = db.list_articles(limit=200, published_only=False)

    print(f"Total articles: {len(articles)}\n")
    changes = []

    for i, article in enumerate(articles):
        current = article.get('topic', 'TECH')
        slug = article.get('slug', '')
        new_cat = classify_article(article)

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
