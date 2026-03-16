"""
Regenerate article keywords using AI.

Sends article title + content to Gemini and asks for 3 noun-only keywords.
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


def _generate_keywords(title: str, content: str) -> list:
    """Ask Gemini to extract 3 noun-only keywords from article."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available")

    clean_text = re.sub(r'<[^>]+>', '', content)
    # Truncate to first 2000 chars to save tokens
    preview = clean_text[:2000]

    prompt = (
        f"다음 기사의 핵심 주제를 대표하는 고유명사/키워드를 정확히 3개만 추출하세요.\n\n"
        f"제목: {title}\n"
        f"본문 일부: {preview}\n\n"
        f"규칙:\n"
        f"- 반드시 고유명사 또는 핵심 주제 명사만 (예: 삼성전자, 반도체, AI)\n"
        f"- 동사 금지 (❌ 있다, 하다, 되다)\n"
        f"- 형용사 금지 (❌ 단순한, 새로운, 숨겨진)\n"
        f"- 조사/부사 금지 (❌ 에서, 으로, 달러는, 어떻게)\n"
        f"- 소유격/조사 붙은 형태 금지 (❌ 대우건설의, 트위치의, 시장의)\n\n"
        f"응답 형식 (이것만 출력):\n"
        f"키워드1, 키워드2, 키워드3"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=100,
        ),
    )
    raw = response.text.strip()
    keywords = [k.strip() for k in raw.split(',') if k.strip()]
    return keywords[:3]


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

        logger.info(f"[{i+1}/{len(articles)}] {title[:50]}...")
        logger.info(f"  Old: {old_kw}")

        try:
            new_kw = _generate_keywords(title, content)
            logger.info(f"  New: {new_kw}")

            if not new_kw:
                logger.warning(f"  SKIP: No keywords generated")
                failed += 1
                continue

            result = db.update_article(slug, {'keywords': new_kw})
            if result:
                success += 1
                logger.info(f"  ✅ Updated")
                _revalidate_slug(slug)
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

    logger.info(f"\n=== Keyword Regeneration Complete ===")
    logger.info(f"Success: {success}, Failed: {failed}")


if __name__ == '__main__':
    main()
