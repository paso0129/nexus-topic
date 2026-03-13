"""
Rewrite article tone: 1인칭 칼럼체 → 3인칭 객관적 분석체

Finds published Korean articles with subjective/first-person writing
and rewrites them in objective analytical tone using Gemini API.

Usage: python -m scripts.rewrite_tone
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

KOREAN_RE = re.compile(r'[\uac00-\ud7a3]')

# 1인칭/주관적 표현 + 합쇼체 감지 패턴
SUBJECTIVE_PATTERNS = [
    r'나는\s',
    r'내가\s',
    r'나의\s',
    r'필자[는가의]',
    r'내\s+생각',
    r'나로서는',
    r'나\s+역시',
    r'우리는\s',
    r'우리가\s',
    r'동의할\s+수\s+없',
    r'오늘\s+내가\s+하려는',
    r'당신[의은는에]',
    r'불편한\s+진실',
    r'축배를\s+들',
    r'솔직히\s+말하',
    r'습니다[.\s]',
    r'합니다[.\s]',
    r'됩니다[.\s]',
    r'있습니다[.\s]',
    r'없습니다[.\s]',
]


def has_subjective_tone(html: str) -> tuple[bool, list[str]]:
    """Check if article has subjective/first-person tone. Returns (bool, matched_patterns)."""
    text = re.sub(r'<[^>]+>', '', html)
    found = []
    for pattern in SUBJECTIVE_PATTERNS:
        if re.search(pattern, text):
            match = re.search(pattern, text)
            # Get surrounding context
            start = max(0, match.start() - 10)
            end = min(len(text), match.end() + 10)
            found.append(text[start:end].strip())
    return len(found) > 0, found


def count_words(html: str) -> int:
    """Count words (어절) in HTML content."""
    text = re.sub(r'<[^>]+>', '', html)
    words = text.split()
    return len([w for w in words if len(w.strip()) > 0])


def calculate_reading_time(html: str) -> int:
    """Calculate reading time in minutes (Korean ~500 chars/min)."""
    text = re.sub(r'<[^>]+>', '', html)
    chars = len(text.replace(' ', '').replace('\n', ''))
    return max(1, round(chars / 500))


def build_rewrite_prompt(title: str, topic: str, content: str) -> str:
    """Build prompt to rewrite article tone."""
    today = datetime.now().strftime('%Y년 %m월 %d일')

    return f"""다음 기사의 톤을 수정하세요. 내용과 구조는 최대한 유지하되, 문체만 변경합니다.

기사 제목: {title}
카테고리: {topic}
오늘 날짜: {today}

현재 기사 내용:
{content}

톤 수정 규칙 (가장 중요):
1. 문체를 반드시 해라체(~다, ~이다, ~했다, ~된다)로 통일. 합쇼체(~습니다, ~합니다) 절대 금지.
2. 절대 1인칭(나, 저, 내가, 필자, 우리) 사용 금지 → 3인칭 객관적 서술로 변환
3. "당신", "여러분" 등 독자 직접 호칭 금지
4. 감정적/선정적 표현 제거: "불편한 진실", "충격적", "놀라운", "축배를 들기엔" 등
5. 개인 의견 → 데이터/전문가 의견으로 전환 (예: "나는 동의할 수 없다" → "이에 대해 전문가들은 다른 시각을 제시한다")
6. 수사적 질문은 유지 가능하되 1인칭 포함된 것은 제거

유지해야 할 것:
- 기존 HTML 구조 (h2, h3, p, ul, ol, strong, em, blockquote)
- 모든 데이터, 숫자, 팩트
- 기사의 핵심 논지와 분석
- 기존 분량 (줄이지 말 것)
- 자주 묻는 질문 섹션 (있으면 유지)
- 키워드 관련 내용

응답 형식:
KEYWORDS: [쉼표로 구분된 키워드 5-8개, 핵심 명사/고유명사만]
CONTENT:
[수정된 HTML 콘텐츠]
"""


def parse_response(response_text: str) -> dict:
    """Parse the rewritten article response."""
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


def main():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    api_key = os.environ.get('GOOGLE_API_KEY')

    if not api_key or not genai:
        logger.error("GOOGLE_API_KEY required")
        return

    supabase = create_client(url, key)
    client = genai.Client(api_key=api_key)

    # Fetch all published Korean articles
    result = supabase.table('articles').select(
        'id, slug, title, content, keywords, topic, meta_description, word_count, published'
    ).eq('published', True).order('created_at', desc=True).execute()

    articles = result.data or []
    korean_articles = [a for a in articles if KOREAN_RE.search(a.get('title', ''))]
    logger.info(f"Published Korean articles: {len(korean_articles)}")

    # Filter articles with subjective tone
    needs_rewrite = []
    for a in korean_articles:
        content = a.get('content', '')
        is_subjective, matches = has_subjective_tone(content)
        if is_subjective:
            needs_rewrite.append((a, matches))
            logger.info(f"  주관적 톤 발견: {a['title'][:40]} — {matches[:3]}")

    logger.info(f"\n톤 수정 필요: {len(needs_rewrite)}개 / 전체 {len(korean_articles)}개")

    if not needs_rewrite:
        logger.info("수정 필요한 기사가 없습니다.")
        return

    rewritten = 0
    failed = 0

    for a, matches in needs_rewrite:
        title = a['title']
        slug = a['slug']
        current_wc = count_words(a.get('content', ''))
        logger.info(f"\n--- {title[:50]} ({current_wc}w) ---")
        logger.info(f"  감지된 패턴: {matches[:3]}")

        prompt = build_rewrite_prompt(title, a.get('topic', ''), a.get('content', ''))

        try:
            logger.info("  Gemini API 호출 중...")
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,  # Low temp for faithful rewriting
                    max_output_tokens=16384,
                ),
            )
            parsed = parse_response(response.text)

            if not parsed['content']:
                logger.error(f"  파싱 실패: 콘텐츠 없음")
                failed += 1
                continue

            new_wc = count_words(parsed['content'])
            reading_time = calculate_reading_time(parsed['content'])

            # Check the rewrite didn't drastically shorten the article
            if new_wc < current_wc * 0.7:
                logger.error(f"  콘텐츠가 너무 짧아짐: {new_wc}w (기존 {current_wc}w)")
                failed += 1
                continue

            # Verify subjective tone is actually removed
            still_subjective, remaining = has_subjective_tone(parsed['content'])
            if still_subjective:
                logger.warning(f"  주관적 표현 잔존: {remaining[:2]} — 그래도 업데이트")

            # Update DB
            update_data = {
                'content': parsed['content'],
                'word_count': new_wc,
                'reading_time': reading_time,
                'updated_at': datetime.now().isoformat(),
            }

            if parsed['keywords']:
                update_data['keywords'] = parsed['keywords']

            supabase.table('articles').update(update_data).eq('id', a['id']).execute()

            logger.info(f"  완료: {current_wc}w → {new_wc}w")
            rewritten += 1

            time.sleep(5)

        except Exception as e:
            logger.error(f"  실패: {e}")
            failed += 1
            time.sleep(10)

    logger.info(f"\n{'='*60}")
    logger.info(f"결과: {rewritten}개 수정, {failed}개 실패")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
