"""
Audit all articles for quality issues:
- Truncated content (low word count or ends mid-sentence)
- Bad keywords (Korean stop words)
- Category mismatch (detect via title heuristics)
- Missing featured image
"""
import os
import re
import json
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

KOREAN_STOP = {
    '있다', '없다', '하다', '되다', '이다', '것이다', '않다', '같다',
    '보다', '주다', '받다', '알다', '모르다', '나다', '오다', '가다',
    '누가', '무엇', '어디', '언제', '어떻게', '왜', '이것', '그것',
    '하지만', '그러나', '그리고', '또한', '그래서', '때문', '위해',
    '통해', '대한', '따른', '현재', '최근', '가장', '이미', '매우',
    '아직', '결국', '실제', '단순', '당신', '우리', '여기', '거기',
    '하는', '되는', '있는', '없는', '같은', '다른', '새로운', '중요한',
    '필요한', '가능한', '실제로', '특히', '이러한', '그러한',
    '정말', '진짜', '아니다', '보는', '닷컴', '강력한',
}

CATEGORY_HINTS = {
    '연예': ['아이돌', 'K-POP', 'kpop', '드라마', '영화', '엔터', '가수', '배우',
             '앨범', '컴백', '데뷔', '팬', 'BTS', '블랙핑크', '엔하이픈', 'ENHYPEN',
             'NCT', 'aespa', '세계관', '뮤직', '콘서트', '음원', '차트', '팬덤'],
    '스포츠': ['야구', '축구', '농구', 'KBO', 'K리그', 'MLB', 'NBA', 'EPL',
              '올림픽', '월드컵', '선수', '감독', '경기', '리그', '프로야구',
              '손흥민', '오타니', '류현진', '김하성', '이강인'],
    '부동산': ['아파트', '전세', '월세', '분양', '청약', '재건축', '부동산',
              'DSR', 'LTV', '주택', '매매', '임대', '시세'],
    'IT·테크': ['AI', '반도체', '클라우드', '삼성전자', '애플', '엔비디아',
               '스타트업', '플랫폼', '소프트웨어', '데이터', '로봇', '자율주행'],
    '글로벌 경제': ['나스닥', 'S&P', '연준', 'Fed', '달러', '유가', '비트코인',
                  '트럼프', '관세', '무역', '중국', '미국 경제', '유럽'],
    '경제': ['코스피', '코스닥', '금리', '환율', '원달러', '기준금리', '한국은행',
            '채권', '국채', '수출', '고용', '실업률', 'GDP', '인플레이션'],
}


def count_korean_words(html: str) -> int:
    """Count Korean words (sequences of Korean chars) in HTML content."""
    text = re.sub(r'<[^>]+>', '', html)
    # Korean words: sequences of Hangul + mixed
    words = re.findall(r'[\uAC00-\uD7A3]+(?:\s*[\uAC00-\uD7A3]+)*|[a-zA-Z0-9]+', text)
    return len(words)


def is_truncated(html: str) -> bool:
    """Check if article content appears truncated."""
    text = re.sub(r'<[^>]+>', '', html).strip()
    if not text:
        return True
    # Ends mid-sentence (no period, question mark, etc.)
    last_char = text[-1]
    if last_char not in '.?!다.):, 」, 』':
        # Check if last sentence is incomplete
        last_line = text.split('\n')[-1].strip()
        if last_line and not last_line[-1] in '.?!다)':
            return True
    return False


def has_bad_keywords(keywords: list) -> list:
    """Return list of bad keywords."""
    bad = []
    for kw in keywords:
        if kw in KOREAN_STOP:
            bad.append(kw)
        # Single Korean char keywords
        if len(kw) == 1:
            bad.append(kw)
    return bad


def suggest_category(title: str, content_text: str) -> str | None:
    """Suggest a category based on title/content keywords."""
    combined = (title + ' ' + content_text[:500]).lower()
    scores = {}
    for cat, hints in CATEGORY_HINTS.items():
        score = sum(1 for h in hints if h.lower() in combined)
        if score > 0:
            scores[cat] = score
    if scores:
        return max(scores, key=scores.get)
    return None


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    # Fetch all articles
    result = supabase.table('articles').select(
        'id, slug, title, content, keywords, topic, word_count, published, featured_image, created_at'
    ).order('created_at', desc=True).execute()
    articles = result.data or []
    logger.info(f"총 기사 수: {len(articles)}")

    issues = []

    for a in articles:
        article_issues = []
        content = a.get('content', '') or ''
        keywords = a.get('keywords', []) or []
        title = a.get('title', '')
        topic = a.get('topic', '')
        word_count = a.get('word_count', 0)
        slug = a.get('slug', '')

        # 1. Check word count
        actual_wc = count_korean_words(content)
        if actual_wc < 400:
            article_issues.append(f"TRUNCATED: word_count={actual_wc} (stored={word_count})")

        # 2. Check if content ends abruptly
        if is_truncated(content):
            article_issues.append("ABRUPT_END: 문장이 완결되지 않음")

        # 3. Check keywords
        bad_kw = has_bad_keywords(keywords)
        if bad_kw:
            article_issues.append(f"BAD_KEYWORDS: {bad_kw}")

        # 4. Check category
        content_text = re.sub(r'<[^>]+>', '', content)
        suggested = suggest_category(title, content_text)
        if suggested and suggested != topic:
            article_issues.append(f"CATEGORY_MISMATCH: current={topic}, suggested={suggested}")

        # 5. Check featured image
        if not a.get('featured_image'):
            article_issues.append("NO_IMAGE")

        # 6. Not published
        if not a.get('published'):
            article_issues.append("UNPUBLISHED")

        if article_issues:
            issues.append({
                'id': a['id'],
                'slug': slug,
                'title': title[:60],
                'topic': topic,
                'word_count': actual_wc,
                'published': a.get('published', False),
                'issues': article_issues,
            })

    # Print report
    logger.info(f"\n{'='*80}")
    logger.info(f"문제 있는 기사: {len(issues)}/{len(articles)}")
    logger.info(f"{'='*80}\n")

    # Group by issue type
    truncated = [i for i in issues if any('TRUNCATED' in x for x in i['issues'])]
    abrupt = [i for i in issues if any('ABRUPT_END' in x for x in i['issues'])]
    bad_kw = [i for i in issues if any('BAD_KEYWORDS' in x for x in i['issues'])]
    cat_mismatch = [i for i in issues if any('CATEGORY_MISMATCH' in x for x in i['issues'])]
    no_image = [i for i in issues if any('NO_IMAGE' in x for x in i['issues'])]
    unpublished = [i for i in issues if any('UNPUBLISHED' in x for x in i['issues'])]

    logger.info(f"--- TRUNCATED ({len(truncated)}개) ---")
    for i in truncated:
        logger.info(f"  [{i['topic']}] {i['title']} (words={i['word_count']})")

    logger.info(f"\n--- ABRUPT_END ({len(abrupt)}개) ---")
    for i in abrupt:
        logger.info(f"  [{i['topic']}] {i['title']}")

    logger.info(f"\n--- BAD_KEYWORDS ({len(bad_kw)}개) ---")
    for i in bad_kw:
        kw_issues = [x for x in i['issues'] if 'BAD_KEYWORDS' in x]
        logger.info(f"  [{i['topic']}] {i['title']}")
        for k in kw_issues:
            logger.info(f"    {k}")

    logger.info(f"\n--- CATEGORY_MISMATCH ({len(cat_mismatch)}개) ---")
    for i in cat_mismatch:
        cat_issues = [x for x in i['issues'] if 'CATEGORY_MISMATCH' in x]
        logger.info(f"  {i['title']}")
        for c in cat_issues:
            logger.info(f"    {c}")

    logger.info(f"\n--- NO_IMAGE ({len(no_image)}개) ---")
    for i in no_image:
        logger.info(f"  [{i['topic']}] {i['title']}")

    logger.info(f"\n--- UNPUBLISHED ({len(unpublished)}개) ---")
    for i in unpublished:
        logger.info(f"  [{i['topic']}] {i['title']} (words={i['word_count']})")

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"  총 기사: {len(articles)}")
    logger.info(f"  문제 기사: {len(issues)}")
    logger.info(f"  잘림(400w 미만): {len(truncated)}")
    logger.info(f"  문장 미완결: {len(abrupt)}")
    logger.info(f"  불량 키워드: {len(bad_kw)}")
    logger.info(f"  카테고리 오류: {len(cat_mismatch)}")
    logger.info(f"  이미지 없음: {len(no_image)}")
    logger.info(f"  미발행: {len(unpublished)}")
    logger.info(f"{'='*80}")

    # Output JSON for downstream processing
    with open('/tmp/audit_result.json', 'w') as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
