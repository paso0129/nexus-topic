"""
Expand short articles (< 1500 words) to meet SEO quality standards.

Fetches articles from DB, sends existing content to Gemini for expansion,
updates DB with expanded content, and triggers ISR revalidation.
"""

import os
import re
import sys
import time
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import requests as http_requests

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from scripts.database import DatabaseClient

MIN_WORDS = 1500
MAX_WORDS = 2000


def count_words(html: str) -> int:
    """Count words in HTML content."""
    text = re.sub(r'<[^>]+>', '', html)
    return len(text.split())


def _build_expand_prompt(article: dict) -> str:
    """Build prompt to expand an existing article."""
    title = article.get('title', '')
    content = article.get('content', '')
    current_words = count_words(content)
    topic = article.get('trending_keyword', title)
    category = article.get('topic', 'TECH')

    # Check if FAQ section exists
    has_faq = bool(re.search(r'<h2[^>]*>\s*Frequently Asked Questions', content, re.IGNORECASE))

    faq_instruction = ""
    if not has_faq:
        faq_instruction = """
MISSING FAQ — You MUST add a FAQ section at the end:
<h2>Frequently Asked Questions</h2>
Then 3-5 Q&A pairs as:
<h3>[Question in natural search query form?]</h3>
<p>[Specific answer with facts — 2-3 sentences]</p>
"""

    return f"""You are expanding an existing article to meet quality standards. The article currently has {current_words} words and needs to be {MIN_WORDS}-{MAX_WORDS} words.

TITLE: {title}
CATEGORY: {category}
ORIGINAL TOPIC: {topic}

EXISTING CONTENT (DO NOT rewrite this — EXPAND it):
{content}

EXPANSION RULES:
1. Keep ALL existing content intact — do NOT remove, rewrite, or rephrase existing paragraphs
2. ADD new sections between existing ones to deepen the analysis:
   - Add more specific data points, statistics, dollar amounts
   - Add a comparison with a previous similar event or competing approach
   - Add an "angle others are missing" section if not present
   - Add more expert context or industry perspective
3. Ensure at least 2 H2 headings are in question form (ending with ?)
4. Add 1-2 more external links to authoritative sources (Wikipedia, Reuters, official sites)
   Use format: <a href="URL" target="_blank" rel="noopener noreferrer">text</a>
5. Do NOT add "Editor's Take:" or "My Prediction:" labels — weave opinions naturally
6. VARY sentence length — mix short punchy sentences with longer analytical ones
7. The expanded article must be {MIN_WORDS}-{MAX_WORDS} words (excluding FAQ)
{faq_instruction}
CRITICAL: Return ONLY the complete HTML content (all existing + new sections merged together). No TITLE/META/CATEGORY headers. Start directly with the first HTML tag.

Format: HTML only (h2, h3, p, ul, ol, strong, em, blockquote, a). No <html>/<head>/<body> tags."""


def _expand_with_gemini(prompt: str) -> str:
    """Call Gemini API to expand article."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available (GOOGLE_API_KEY missing)")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.6,
            max_output_tokens=8192,
        ),
    )
    return response.text


def _revalidate_slug(slug: str):
    """Revalidate ISR cache for a specific article."""
    secret = os.getenv('REVALIDATION_SECRET', '')
    if not secret:
        return
    try:
        resp = http_requests.post(
            "https://www.nexustopic.com/api/revalidate",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            json={"paths": [f"/article/{slug}"]},
            timeout=10,
        )
        logger.info(f"  Revalidated /article/{slug}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"  Revalidation failed for {slug}: {e}")


def main():
    db = DatabaseClient()

    # Fetch all articles
    logger.info("Fetching all articles from DB...")
    all_articles = db.list_articles(limit=200, published_only=True)
    logger.info(f"Total articles: {len(all_articles)}")

    # Filter short articles
    short_articles = []
    for a in all_articles:
        wc = a.get('word_count') or count_words(a.get('content', ''))
        if wc < MIN_WORDS:
            short_articles.append((a, wc))

    if not short_articles:
        logger.info(f"All articles meet the {MIN_WORDS} word minimum!")
        return

    # Sort by word count (shortest first — most improvement needed)
    short_articles.sort(key=lambda x: x[1])

    logger.info(f"Found {len(short_articles)} articles under {MIN_WORDS} words")
    for a, wc in short_articles:
        logger.info(f"  {wc:>5} words | {a.get('slug', '')[:60]}")

    success = 0
    failed = 0
    skipped = 0

    for i, (article, old_wc) in enumerate(short_articles):
        slug = article.get('slug', '')
        title = article.get('title', '')[:50]
        logger.info(f"\n[{i+1}/{len(short_articles)}] Expanding: {title}... ({old_wc} words)")

        try:
            prompt = _build_expand_prompt(article)
            expanded_content = _expand_with_gemini(prompt)

            # Clean up: remove markdown code fences if Gemini wraps in ```html
            expanded_content = re.sub(r'^```html?\s*\n?', '', expanded_content.strip())
            expanded_content = re.sub(r'\n?```\s*$', '', expanded_content.strip())

            new_wc = count_words(expanded_content)
            logger.info(f"  Expanded: {old_wc} → {new_wc} words")

            # Sanity checks
            if new_wc < old_wc:
                logger.warning(f"  SKIP: Expanded version is shorter ({new_wc} < {old_wc})")
                skipped += 1
                continue

            if new_wc < MIN_WORDS * 0.8:
                logger.warning(f"  SKIP: Still too short after expansion ({new_wc} words)")
                skipped += 1
                continue

            # Update DB
            result = db.update_article(slug, {
                'content': expanded_content,
                'word_count': new_wc,
            })

            if result:
                success += 1
                logger.info(f"  ✅ DB updated: {slug}")
                _revalidate_slug(slug)
            else:
                failed += 1
                logger.error(f"  ❌ DB update failed: {slug}")

        except Exception as e:
            failed += 1
            if '429' in str(e) or 'quota' in str(e).lower():
                logger.warning(f"  Rate limit hit, waiting 60s...")
                time.sleep(60)
            else:
                logger.error(f"  Error expanding {slug}: {e}")

        # Rate limit between API calls
        if i < len(short_articles) - 1:
            time.sleep(5)

    logger.info(f"\n=== Expansion Complete ===")
    logger.info(f"Success: {success}, Failed: {failed}, Skipped: {skipped}")
    logger.info(f"Total: {len(short_articles)} articles processed")


if __name__ == '__main__':
    main()
