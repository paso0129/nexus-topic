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
        f"다음 기사를 읽고 세 가지를 답하세요.\n\n"
        f"제목: {title}\n"
        f"본문 일부: {preview}\n\n"
        f"1. 이 기사의 주요 대상이 한국 국내인가, 해외인가?\n"
        f"   - DOMESTIC: 한국 국내 기업, 한국 정책, 한국 시장이 주제 (예: 코스피, 삼성전자, 한국은행)\n"
        f"   - GLOBAL: 해외 기업, 해외 인물, 해외 시장, 국제 이슈가 주제 (예: 비트코인, 달러, 네타냐후, 파키스탄, 나스닥)\n\n"
        f"2. 카테고리: 아래 6개 중 하나\n"
        f"   경제, IT·테크, 글로벌 경제, 부동산, 연예, 스포츠\n"
        f"   규칙: 1번에서 DOMESTIC이면 경제, GLOBAL이면 글로벌 경제 (IT·테크/부동산/연예/스포츠는 별도)\n\n"
        f"3. 키워드: 기사 핵심 주제를 대표하는 고유명사/명사 정확히 3개\n"
        f"   - 반드시 완전한 단어 (2글자 이상). 절대 단어를 자르지 마세요\n"
        f"   - ✅ 좋은 예: 대우건설, 주가, 성장동력 / 비트코인, 암호화폐, 투자\n"
        f"   - ❌ 나쁜 예: 주, 건, 비트코 (잘림) / 있다, 새로운 (동사/형용사)\n\n"
        f"응답 형식 (반드시 세 줄 모두 출력):\n"
        f"SCOPE: DOMESTIC 또는 GLOBAL\n"
        f"TAGS: 키워드1, 키워드2, 키워드3\n"
        f"CATEGORY: 카테고리"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=2048,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    raw = response.text.strip()
    logger.info(f"  Raw AI response: {raw}")

    # Parse scope (DOMESTIC/GLOBAL)
    scope_match = re.search(r'SCOPE[:\s]*(DOMESTIC|GLOBAL)', raw, re.IGNORECASE)
    scope = scope_match.group(1).upper() if scope_match else None
    logger.info(f"  Scope: {scope}")

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

    # If scope is GLOBAL but category is 경제, force to 글로벌 경제
    if scope == 'GLOBAL' and category == '경제':
        logger.info(f"  Scope=GLOBAL + Category=경제 → 글로벌 경제로 보정")
        category = '글로벌 경제'

    # Parse keywords - flexible matching
    tags_match = re.search(r'(?:TAGS|키워드|태그)[:\s]*(.+)', raw, re.IGNORECASE)
    keywords = []
    if tags_match:
        raw_tags = tags_match.group(1).strip()
        keywords = [k.strip().strip('"\'[]') for k in raw_tags.split(',') if len(k.strip().strip('"\'[]')) >= 2][:3]
    else:
        # Fallback: if no TAGS label, try last line as comma-separated keywords
        lines = raw.strip().split('\n')
        if len(lines) >= 2:
            last_line = lines[-1].strip()
            if ',' in last_line and not last_line.startswith('CATEGORY'):
                keywords = [k.strip().strip('"\'[]') for k in last_line.split(',') if len(k.strip().strip('"\'[]')) >= 2][:3]

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
