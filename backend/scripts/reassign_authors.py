"""
Reassign article authors based on category.

Updates the author JSONB field for all published Korean articles
to match the category-author mapping:
  경제, 글로벌 경제 → 송민재
  IT·테크, 부동산   → 정상열
  연예, 스포츠      → 임새봄

Usage: python -m scripts.reassign_authors
"""
import os
import re
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

KOREAN_RE = re.compile(r'[\uac00-\ud7a3]')

AUTHORS = {
    '송민재': {'name': '송민재', 'bio': '거시경제, 금융시장, 환율·금리 동향을 데이터 기반으로 분석합니다.'},
    '임새봄': {'name': '임새봄', 'bio': '반도체, AI, 클라우드 등 IT·테크 산업을 데이터 기반으로 분석합니다.'},
    '정상열': {'name': '정상열', 'bio': '부동산, 엔터테인먼트, 스포츠 산업을 비즈니스 시각으로 분석합니다.'},
}

CATEGORY_AUTHOR_MAP = {
    '경제': '송민재',
    '글로벌 경제': '송민재',
    'IT·테크': '임새봄',
    '부동산': '정상열',
    '연예': '정상열',
    '스포츠': '정상열',
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
        topic = a.get('topic', '')
        author_name = CATEGORY_AUTHOR_MAP.get(topic, '송민재')
        author_data = AUTHORS[author_name]

        current_author = a.get('author', {}) or {}
        if current_author.get('name') == author_name:
            continue

        supabase.table('articles').update({
            'author': author_data,
        }).eq('id', a['id']).execute()

        old_name = current_author.get('name', '(없음)')
        logger.info(f"  {a['title'][:40]} [{topic}]: {old_name} → {author_name}")
        updated += 1

    logger.info(f"\n결과: {updated}개 기사 저자 재배정 완료")


if __name__ == '__main__':
    main()
