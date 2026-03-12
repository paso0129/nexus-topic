"""
Expand truncated Korean articles using Gemini API.
- Regenerates full content (1500-2200 words) keeping same title/topic
- Generates proper keywords via AI
- Fixes category mismatches
- Updates DB in-place
"""
import os
import re
import logging
import time
from datetime import datetime
from supabase import create_client

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

VALID_CATEGORIES = ['경제', 'IT·테크', '글로벌 경제', '부동산', '연예', '스포츠']

KOREAN_RE = re.compile(r'[\uac00-\ud7a3]')

CATEGORY_HINTS = {
    '연예': ['아이돌', 'K-POP', '드라마', '영화', '엔터', '가수', '배우',
             '앨범', '컴백', '데뷔', '팬', '엔하이픈', '세계관', '뮤직', '콘서트', '팬덤'],
    '스포츠': ['야구', '축구', '농구', 'KBO', 'K리그', 'MLB', 'NBA',
              '올림픽', '월드컵', '선수', '감독', '경기', '리그', '프로야구'],
    '부동산': ['아파트', '전세', '월세', '분양', '청약', '재건축', '부동산', '주택', '매매', '시세'],
    'IT·테크': ['AI', '반도체', '클라우드', '삼성전자', '애플', '엔비디아',
               '스타트업', '플랫폼', '소프트웨어', '로봇', '자율주행'],
    '글로벌 경제': ['나스닥', 'S&P', '연준', 'Fed', '달러', '유가', '비트코인',
                  '트럼프', '관세', '무역', '미국 경제'],
    '경제': ['코스피', '코스닥', '금리', '환율', '원달러', '기준금리', '한국은행',
            '채권', '국채', '수출', '고용', '실업률'],
}


def suggest_category(title: str, content_text: str, current: str) -> str:
    """Suggest best category. Only override if clearly wrong."""
    combined = (title + ' ' + content_text[:500]).lower()
    scores = {}
    for cat, hints in CATEGORY_HINTS.items():
        score = sum(1 for h in hints if h.lower() in combined)
        if score > 0:
            scores[cat] = score

    if not scores:
        return current

    best = max(scores, key=scores.get)
    best_score = scores[best]
    current_score = scores.get(current, 0)

    # Only suggest change if the best category scores significantly higher
    if best != current and best_score >= current_score + 2:
        return best
    return current


def build_expand_prompt(title: str, topic: str, meta_description: str) -> str:
    """Build prompt to regenerate article content."""
    today = datetime.now().strftime('%Y년 %m월 %d일')

    return f"""기존 기사를 보강하여 완전한 심층 분석 기사를 작성하세요.

기사 제목: {title}
카테고리: {topic}
메타 설명: {meta_description}
오늘 날짜: {today}

요구사항:
- 분량: 1500-2200 어절 (반드시 충족)
- 언어: 한국어
- 형식: HTML만 (h2, h3, p, ul, ol, strong, em, blockquote). <html>/<head>/<body> 태그 없음
- 톤: 전문 칼럼니스트 — 데이터 기반, 의견 있는 분석
- 대상 독자: 한국 25-45세 직장인·투자자

글쓰기 규칙:
- 절대 "~에 나섰다", "~이 화두다", "~이 주목받고 있다"로 시작하지 마세요
- 금지 표현: "귀추가 주목된다", "지켜봐야 할 것이다", "결론적으로", "주목할 만하다", "패러다임", "게임체인저"
- 문장 길이 극적 변화: 짧은 문장(5-10자)과 긴 분석 문장 혼합
- 1인칭 자연스럽게 사용
- 구체적 숫자, 날짜, 퍼센트, 금액 포함
- 수사적 질문 활용
- 강하고 구체적인 결론

구조:
1. 도입부 — 임팩트 있는 시작 (2-3문단)
2. 본문 — H2 섹션 4-6개, 각 섹션에 데이터/분석 (H2 중 최소 2개는 질문형)
3. 결론 — 핵심 인사이트와 전망
4. 자주 묻는 질문 — H2 아래 3-5개 Q&A (h3 + p)

응답 형식:
KEYWORDS: [쉼표로 구분된 키워드 5-8개, 핵심 명사/고유명사만]
CONTENT:
[HTML 콘텐츠]
"""


def parse_expanded_response(response_text: str) -> dict:
    """Parse the expanded article response."""
    keywords_match = re.search(r'KEYWORDS:\s*(.+?)(?:\n|CONTENT:)', response_text, re.IGNORECASE)
    content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.IGNORECASE | re.DOTALL)

    keywords = []
    if keywords_match:
        raw = keywords_match.group(1).strip().strip('[]')
        keywords = [k.strip().strip('#') for k in raw.split(',') if k.strip()]

    content = ''
    if content_match:
        content = content_match.group(1).strip()

    return {'keywords': keywords, 'content': content}


def count_words(html: str) -> int:
    """Count words in HTML content."""
    text = re.sub(r'<[^>]+>', '', html)
    words = re.findall(r'[\uAC00-\uD7A3]+(?:\s*[\uAC00-\uD7A3]+)*|[a-zA-Z0-9]+', text)
    return len(words)


def calculate_reading_time(html: str) -> int:
    """Calculate reading time in minutes (Korean ~500 chars/min)."""
    text = re.sub(r'<[^>]+>', '', html)
    chars = len(text.replace(' ', '').replace('\n', ''))
    return max(1, round(chars / 500))


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    api_key = os.environ.get('GOOGLE_API_KEY')

    if not api_key or not genai:
        logger.error("GOOGLE_API_KEY required")
        return

    supabase = create_client(url, key)
    client = genai.Client(api_key=api_key)

    # Fetch published Korean articles (the 10 truncated ones)
    result = supabase.table('articles').select(
        'id, slug, title, content, keywords, topic, meta_description, word_count, published'
    ).eq('published', True).order('created_at', desc=True).execute()

    articles = result.data or []
    # Filter Korean articles only
    korean_articles = [a for a in articles if KOREAN_RE.search(a.get('title', ''))]
    logger.info(f"Found {len(korean_articles)} published Korean articles")

    expanded = 0
    failed = 0

    for a in korean_articles:
        title = a['title']
        slug = a['slug']
        current_wc = count_words(a.get('content', ''))
        logger.info(f"\n--- {title[:50]} (현재 {current_wc}w) ---")

        if current_wc >= 800:
            logger.info("  이미 충분한 길이, 스킵")
            continue

        # Fix category if needed
        content_text = re.sub(r'<[^>]+>', '', a.get('content', ''))
        new_topic = suggest_category(title, content_text, a.get('topic', ''))
        if new_topic != a.get('topic', ''):
            logger.info(f"  카테고리 수정: {a['topic']} → {new_topic}")

        # Generate expanded content
        prompt = build_expand_prompt(title, new_topic, a.get('meta_description', ''))

        try:
            logger.info("  Gemini API 호출 중...")
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=8192,
                ),
            )
            parsed = parse_expanded_response(response.text)

            if not parsed['content']:
                logger.error(f"  파싱 실패: 콘텐츠 없음")
                failed += 1
                continue

            new_wc = count_words(parsed['content'])
            reading_time = calculate_reading_time(parsed['content'])

            if new_wc < 400:
                logger.error(f"  생성된 콘텐츠가 너무 짧음: {new_wc}w")
                failed += 1
                continue

            # Update DB
            update_data = {
                'content': parsed['content'],
                'word_count': new_wc,
                'reading_time': reading_time,
                'updated_at': datetime.now().isoformat(),
                'topic': new_topic,
            }

            if parsed['keywords']:
                update_data['keywords'] = parsed['keywords']

            supabase.table('articles').update(update_data).eq('id', a['id']).execute()

            logger.info(f"  완료: {current_wc}w → {new_wc}w, 키워드: {parsed['keywords'][:5]}")
            expanded += 1

            # Rate limit: wait between requests
            time.sleep(5)

        except Exception as e:
            logger.error(f"  실패: {e}")
            failed += 1
            time.sleep(10)

    logger.info(f"\n{'='*60}")
    logger.info(f"결과: {expanded}개 보강, {failed}개 실패")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
