"""
Regenerate article keywords and category using AI.

Sends article title + content to Gemini and asks for:
- 3 noun-only keywords
- Correct category from 6 options
Updates DB and triggers ISR revalidation.
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

VALID_CATEGORIES = ['경제', 'IT·테크', '글로벌 경제', '부동산', '연예', '스포츠']


def _generate_keywords_and_category(title: str, content: str) -> dict:
    """Ask Gemini to extract 3 keywords + correct category from article."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available")

    clean_text = re.sub(r'<[^>]+>', '', content)
    preview = clean_text[:2000]

    prompt = (
        f"다음 기사를 읽고 두 가지를 답하세요.\n\n"
        f"제목: {title}\n"
        f"본문 일부: {preview}\n\n"
        f"1. 카테고리: 아래 6개 중 가장 적합한 하나를 골라주세요\n"
        f"   경제, IT·테크, 글로벌 경제, 부동산, 연예, 스포츠\n\n"
        f"2. 키워드: 기사 핵심 주제를 대표하는 고유명사/명사 정확히 3개\n"
        f"   - 고유명사 또는 핵심 주제 명사만 (예: 삼성전자, 반도체, AI)\n"
        f"   - 동사 금지 (❌ 있다, 하다, 되다)\n"
        f"   - 형용사 금지 (❌ 단순한, 새로운, 숨겨진)\n"
        f"   - 조사/부사 금지 (❌ 에서, 으로, 달러는, 어떻게)\n"
        f"   - 소유격 금지 (❌ 대우건설의, 트위치의)\n\n"
        f"응답 형식 (반드시 두 줄 모두 출력):\n"
        f"TAGS: 키워드1, 키워드2, 키워드3\n"
        f"CATEGORY: 카테고리"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=256,
        ),
    )
    raw = response.text.strip()
    logger.info(f"  Raw AI response: {raw}")

    # Parse category - flexible matching
    cat_match = re.search(r'(?:CATEGORY|카테고리)[:\s]*(.+)', raw, re.IGNORECASE)
    category = None
    if cat_match:
        cat = cat_match.group(1).strip().rstrip('.')
        # Fuzzy match category names
        for valid_cat in VALID_CATEGORIES:
            if valid_cat in cat or cat in valid_cat:
                category = valid_cat
                break

    # Parse keywords - flexible matching
    tags_match = re.search(r'(?:TAGS|키워드|태그)[:\s]*(.+)', raw, re.IGNORECASE)
    keywords = []
    if tags_match:
        raw_tags = tags_match.group(1).strip()
        keywords = [k.strip().strip('"\'') for k in raw_tags.split(',') if k.strip()][:3]
    else:
        # Fallback: if no TAGS label, try last line as comma-separated keywords
        lines = raw.strip().split('\n')
        if len(lines) >= 2:
            last_line = lines[-1].strip()
            if ',' in last_line and not last_line.startswith('CATEGORY'):
                keywords = [k.strip().strip('"\'') for k in last_line.split(',') if k.strip()][:3]

    return {'keywords': keywords, 'category': category}


def _revalidate(slug: str = "", all_articles: bool = False):
    """Revalidate ISR cache."""
    secret = os.getenv('REVALIDATION_SECRET', '')
    if not secret:
        return
    try:
        payload = {}
        if slug:
            payload["slug"] = slug
        if all_articles:
            payload["all_articles"] = True
        resp = http_requests.post(
            "https://www.nexustopic.com/api/revalidate",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        label = f"/article/{slug}" if slug else "all articles"
        logger.info(f"  Revalidated {label}: {resp.status_code}")
    except Exception as e:
        logger.warning(f"  Revalidation failed: {e}")


def main():
    db = DatabaseClient()

    logger.info("Fetching all published articles...")
    articles = db.list_articles(limit=200, published_only=True)
    logger.info(f"Total: {len(articles)} articles")

    success = 0
    failed = 0

    for i, article in enumerate(articles):
        slug = article.get('slug', '')
        title = article.get('title', '')
        content = article.get('content', '')
        old_kw = article.get('keywords', [])
        old_cat = article.get('topic', '')

        logger.info(f"[{i+1}/{len(articles)}] {title[:50]}...")
        logger.info(f"  Old keywords: {old_kw}")
        logger.info(f"  Old category: {old_cat}")

        try:
            result = _generate_keywords_and_category(title, content)
            new_kw = result['keywords']
            new_cat = result['category']

            logger.info(f"  New keywords: {new_kw}")
            logger.info(f"  New category: {new_cat}")

            if not new_kw:
                logger.warning(f"  SKIP: No keywords generated")
                failed += 1
                continue

            update_data = {'keywords': new_kw}
            if new_cat and new_cat != old_cat:
                update_data['topic'] = new_cat
                logger.info(f"  Category changed: {old_cat} → {new_cat}")

            db_result = db.update_article(slug, update_data)
            if db_result:
                success += 1
                logger.info(f"  ✅ Updated")
                _revalidate(slug=slug)
            else:
                failed += 1
                logger.error(f"  ❌ DB update failed")

        except Exception as e:
            failed += 1
            if '429' in str(e) or 'quota' in str(e).lower():
                logger.warning(f"  Rate limit, waiting 30s...")
                time.sleep(30)
            else:
                logger.error(f"  Error: {e}")

        # Rate limit
        time.sleep(2)

    logger.info(f"\n=== Keyword & Category Regeneration Complete ===")
    logger.info(f"Success: {success}, Failed: {failed}")

    if success > 0:
        logger.info("Revalidating all pages...")
        _revalidate(all_articles=True)


if __name__ == '__main__':
    main()
