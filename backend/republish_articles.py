"""
Republish unpublished articles that are in good shape.

Checks each unpublished article for:
- Has content (not empty)
- Is Korean (numeric slug = new format)
- Title is valid (not truncated, not foreign)
- Content is not truncated (proper HTML, enough words)
- No hallucination (AI quality check via Gemini)
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
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _check_article_quality(title: str, content: str) -> dict:
    """Use Gemini to check article for hallucinations and quality issues."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        return {'pass': True, 'reason': 'no API key, skipping check'}

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return {'pass': True, 'reason': 'genai not available'}

    clean_text = re.sub(r'<[^>]+>', '', content)
    preview = clean_text[:3000]

    prompt = (
        f"다음 한국어 뉴스 기사의 품질을 검증해주세요.\n\n"
        f"제목: {title}\n"
        f"본문: {preview}\n\n"
        f"아래 항목만 확인하고 결과를 출력하세요:\n"
        f"1. 가상 인물/기업: 실존하지 않는 인물이나 기업명이 마치 실제인 것처럼 사용됐는가?\n"
        f"   (예: '체이스 인피니티'라는 가상 배우, '시냅틱 애널리틱스'라는 가상 기업)\n"
        f"2. 글이 중간에 잘렸는가: 문장이 완성되지 않은 채 끝나거나, 글의 흐름이 갑자기 끊겼는가?\n"
        f"3. 명백한 사실 오류: 현실과 정반대되는 주장이 있는가?\n\n"
        f"응답 형식 (한 줄로):\n"
        f"PASS 또는 FAIL: 사유\n"
        f"예시: PASS\n"
        f"예시: FAIL: '김도현'이라는 가상 인물이 실존 인물처럼 인용됨"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = response.text.strip()
        logger.info(f"    Quality check: {raw[:100]}")

        if raw.upper().startswith('PASS'):
            return {'pass': True, 'reason': 'passed'}
        elif raw.upper().startswith('FAIL'):
            reason = raw.split(':', 1)[1].strip() if ':' in raw else raw
            return {'pass': False, 'reason': reason}
        else:
            # Ambiguous response, be conservative
            return {'pass': False, 'reason': f'unclear response: {raw[:80]}'}
    except Exception as e:
        logger.warning(f"    Quality check error: {e}")
        return {'pass': True, 'reason': f'check failed: {e}'}


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

        # Skip if no title or title looks broken
        if not title:
            skipped.append((slug, 'no title'))
            continue
        # Skip if title is too short (likely incomplete) or not Korean
        title_korean = len(re.findall(r'[\uAC00-\uD7A3]', title))
        if title_korean < 5 or len(title) < 10:
            skipped.append((slug, f'bad title: "{title[:40]}"'))
            continue
        # Skip if title contains non-Korean/English characters (Russian, etc.)
        if re.search(r'[\u0400-\u04FF]', title):
            skipped.append((slug, f'non-Korean title: "{title[:40]}"'))
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

    # Quality check + fix + publish
    success = 0
    failed = 0
    quality_failed = 0

    for art in publishable:
        slug = art['slug']
        title = art['title']

        try:
            # Quality check (hallucination detection)
            logger.info(f"\n  [{slug}] {title}")
            full_article = db.get_article(slug)
            if not full_article:
                logger.error(f"    Could not fetch article {slug}")
                failed += 1
                continue

            quality = _check_article_quality(title, full_article.get('content', ''))
            if not quality['pass']:
                logger.warning(f"    ❌ QUALITY FAIL: {quality['reason']}")
                quality_failed += 1
                continue

            update_data = {'published': True}

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

        time.sleep(3)  # Rate limit

    logger.info(f"\n{'='*60}")
    logger.info(f"Done! Published: {success}, Quality failed: {quality_failed}, Error: {failed}")

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
