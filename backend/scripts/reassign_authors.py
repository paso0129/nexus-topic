"""
Reassign article authors to unified editorial team.

Updates the author JSONB field for all published Korean articles
to use the NexusTopic editorial team instead of individual fake personas.

Usage: python -m scripts.reassign_authors
"""
import os
import re
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

KOREAN_RE = re.compile(r'[\uac00-\ud7a3]')

EDITORIAL_AUTHOR = {
    'name': 'NexusTopic 편집팀',
    'bio': 'AI를 활용하여 트렌딩 이슈를 데이터 기반으로 분석하고, 편집팀이 팩트체크와 최종 검토를 수행합니다.',
}


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    result = supabase.table('articles').select(
        'id, slug, title, topic, author, published'
    ).eq('published', True).execute()

    articles = result.data or []
    korean_articles = [a for a in articles if KOREAN_RE.search(a.get('title', ''))]
    logger.info(f"Published Korean articles: {len(korean_articles)}")

    updated = 0
    for a in korean_articles:
        current_author = a.get('author', {}) or {}
        if current_author.get('name') == EDITORIAL_AUTHOR['name']:
            continue

        supabase.table('articles').update({
            'author': EDITORIAL_AUTHOR,
        }).eq('id', a['id']).execute()

        old_name = current_author.get('name', '(없음)')
        logger.info(f"  {a['title'][:40]}: {old_name} → {EDITORIAL_AUTHOR['name']}")
        updated += 1

    logger.info(f"\n결과: {updated}개 기사 저자 재배정 완료")


if __name__ == '__main__':
    main()
