"""
Content Generator using Gemini

Generates SEO-optimized blog articles using:
- Primary: Gemini 3.1 Pro Preview via CLI (Google account auth, no API quota)
- Fallback: Gemini 2.5 Pro via API (free tier)
"""

import logging
import os
import random
import re
import subprocess
import shutil
import time
from typing import Dict, Optional
from datetime import datetime

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    import anthropic
except ImportError:
    anthropic = None

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Stopwords to ignore during similarity comparison
_STOPWORDS = frozenset([
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'about', 'between',
    'through', 'after', 'before', 'during', 'and', 'but', 'or', 'not',
    'no', 'nor', 'so', 'yet', 'both', 'either', 'neither', 'each',
    'every', 'all', 'any', 'few', 'more', 'most', 'other', 'some',
    'such', 'than', 'too', 'very', 'just', 'because', 'if', 'when',
    'how', 'what', 'why', 'where', 'who', 'which', 'that', 'this',
    'it', 'its', 'you', 'your', 'we', 'our', 'they', 'their', 'them',
    'he', 'she', 'his', 'her', 'my', 'me', 'up', 'out', 'new',
    # 한국어 불용어
    '이', '그', '저', '것', '수', '등', '및', '또', '더', '위해',
    '대한', '통해', '따른', '관련', '대해', '중인', '있는', '하는',
    '된다', '있다', '한다', '이다', '된다',
])

# Gemini CLI path (cached)
_gemini_cli_path = shutil.which('gemini')


def _generate_with_gemini_cli(prompt: str, model: str = "gemini-3.1-pro-preview") -> str:
    """Generate content using Gemini CLI (uses Google account auth, no API quota)."""
    if not _gemini_cli_path:
        raise RuntimeError("Gemini CLI not installed")

    logger.info(f"Calling Gemini CLI ({model})...")
    result = subprocess.run(
        [_gemini_cli_path, '-m', model, '-p', prompt],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Gemini CLI error: {result.stderr.strip()}")

    # Filter out CLI status lines
    lines = result.stdout.strip().split('\n')
    content_lines = [l for l in lines
                     if not l.startswith('Loaded cached')
                     and not l.startswith('Hook registry')]
    return '\n'.join(content_lines)


def _get_genai_client():
    """Get or create a Gemini API client."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available")
    return genai.Client(api_key=api_key)


def _generate_with_gemini_api(
    prompt: str,
    model_name: str = "gemini-3.1-pro-preview",
    use_search: bool = True,
) -> str:
    """Generate content using Google Gemini API with Google Search grounding."""
    client = _get_genai_client()
    logger.info(f"Calling Gemini API ({model_name}, search={'on' if use_search else 'off'})...")

    config_kwargs = {
        'temperature': 0.7,
        'max_output_tokens': 16384,
    }
    if use_search:
        config_kwargs['tools'] = [
            genai_types.Tool(google_search=genai_types.GoogleSearch())
        ]

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )
    return response.text


def _is_similar(text_a: str, text_b: str, threshold: float = 0.35) -> bool:
    """Check if two texts are similar using word overlap (Jaccard similarity)."""
    def extract_words(text):
        words = set(re.findall(r'[\uAC00-\uD7A3]+|[a-z0-9]+', text.lower()))
        return {w for w in words if len(w) > 1 and w not in _STOPWORDS}

    words_a = extract_words(text_a)
    words_b = extract_words(text_b)

    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    union = words_a | words_b

    similarity = len(intersection) / len(union) if union else 0

    if words_a.issubset(words_b) or words_b.issubset(words_a):
        return True

    return similarity >= threshold


def _is_semantic_duplicate(new_title: str, existing_titles: set) -> bool:
    """Use LLM to check if a generated article title covers the EXACT same specific story as any existing article."""
    try:
        titles_list = '\n'.join(list(existing_titles)[:50])
        prompt = (
            f'Does this new article title cover the EXACT SAME specific story, event, or announcement as any existing article?\n\n'
            f'IMPORTANT: Two articles about the same broad category (e.g., both about "stock market" or "cryptocurrency") '
            f'are NOT duplicates. They must be about the SAME specific event, company announcement, or news story.\n\n'
            f'New title: {new_title}\n\n'
            f'Existing titles:\n{titles_list}\n\n'
            f'Reply ONLY "YES" or "NO".'
        )

        # Try Gemini API first (fast, lightweight task — no search needed)
        try:
            resp_text = _generate_with_gemini_api(prompt, use_search=False)
            answer = resp_text.strip().upper()
            time.sleep(3)
            if answer == 'YES':
                logger.info(f"Semantic duplicate detected (Gemini API): '{new_title}'")
                return True
            return False
        except Exception as e:
            logger.warning(f"Gemini API dedup check failed: {e}")

        # Fallback to Gemini CLI
        try:
            resp_text = _generate_with_gemini_cli(prompt, model="gemini-2.5-flash")
            answer = resp_text.strip().upper()
            if answer == 'YES':
                logger.info(f"Semantic duplicate detected (Gemini CLI): '{new_title}'")
                return True
            return False
        except Exception as e:
            logger.warning(f"Gemini CLI dedup check failed: {e}")

        return False
    except Exception as e:
        logger.warning(f"Semantic duplicate check failed: {e}")
        return False


def calculate_reading_time(text: str, words_per_minute: int = 150) -> int:
    """Calculate estimated reading time for text."""
    clean_text = re.sub(r'<[^>]+>', '', text)
    word_count = len(clean_text.split())
    reading_time = max(1, round(word_count / words_per_minute))
    return reading_time


STOP_WORDS = {
    'this', 'that', 'with', 'from', 'which', 'their', 'there', 'these',
    'those', 'then', 'than', 'them', 'they', 'been', 'being', 'were',
    'have', 'having', 'does', 'doing', 'done', 'will', 'would', 'could',
    'should', 'might', 'must', 'shall', 'about', 'above', 'after', 'again',
    'also', 'another', 'back', 'because', 'before', 'between', 'both',
    'came', 'come', 'each', 'even', 'every', 'find', 'first', 'found',
    'give', 'going', 'gone', 'good', 'great', 'help', 'here', 'high',
    'however', 'into', 'just', 'keep', 'know', 'known', 'last', 'left',
    'like', 'line', 'long', 'look', 'made', 'make', 'many', 'more',
    'most', 'much', 'need', 'never', 'next', 'only', 'open', 'other',
    'over', 'part', 'point', 'really', 'right', 'same', 'seem', 'show',
    'side', 'since', 'small', 'some', 'something', 'still', 'such',
    'sure', 'take', 'tell', 'thing', 'think', 'through', 'time', 'turn',
    'under', 'upon', 'used', 'using', 'very', 'want', 'well', 'what',
    'when', 'where', 'while', 'work', 'world', 'year', 'your',
    'able', 'allow', 'around', 'away', 'become', 'best', 'better',
    'call', 'case', 'change', 'clear', 'close', 'consider', 'create',
    'current', 'different', 'down', 'early', 'else', 'enough', 'ever',
    'example', 'face', 'fact', 'feel', 'form', 'full', 'further',
    'general', 'gets', 'given', 'goes', 'hand', 'hard', 'head',
    'home', 'house', 'human', 'important', 'include', 'issue', 'itself',
    'kind', 'large', 'late', 'lead', 'least', 'less', 'level', 'life',
    'likely', 'live', 'local', 'makes', 'matter', 'mean', 'means',
    'move', 'name', 'near', 'number', 'offer', 'often', 'order',
    'place', 'plan', 'play', 'possible', 'power', 'problem', 'provide',
    'public', 'question', 'quite', 'read', 'real', 'reason', 'result',
    'room', 'said', 'says', 'second', 'sense', 'service', 'several',
    'simply', 'sort', 'start', 'state', 'story', 'system', 'term',
    'things', 'thought', 'today', 'together', 'took', 'true', 'until',
    'ways', 'whole', 'word', 'words', 'wrote', 'years',
    'also', 'already', 'always', 'among', 'based', 'bring', 'built',
    'called', 'comes', 'common', 'complete', 'control', 'design',
    'developed', 'doesn', 'during', 'either', 'enable', 'entire',
    'exactly', 'feature', 'features', 'following', 'ground', 'group',
    'growing', 'itself', 'major', 'making', 'model', 'models',
    'modern', 'natural', 'needs', 'original', 'particularly',
    'people', 'potential', 'rather', 'remain', 'running', 'single',
    'specific', 'support', 'taken', 'three', 'toward', 'towards',
    'type', 'types', 'understanding', 'without',
    'adsbygoogle', 'window', 'push', 'pagead', 'script', 'class',
    'style', 'href', 'http', 'https', 'data', 'content', 'users',
    # 한국어 불용어 — 조사, 어미, 접속사, 의존명사, 일반 동사/형용사
    '있다', '없다', '하다', '되다', '이다', '않다', '받다', '보다', '가다', '오다',
    '있는', '없는', '하는', '되는', '있을', '없을', '하고', '되고', '있고', '없고',
    '에서', '으로', '에게', '부터', '까지', '처럼', '만큼', '대해', '통해', '위해',
    '대한', '따른', '관련', '의한', '인한', '따라', '관한',
    '그리고', '하지만', '그러나', '또한', '그래서', '따라서', '그런데', '왜냐하면',
    '것이다', '것으로', '것이', '수있', '것은', '것을', '것에',
    '이번', '최근', '현재', '올해', '지난', '당시', '이후', '이전',
    '매우', '가장', '모든', '다른', '같은', '이런', '그런', '어떤',
    '이를', '이에', '그를', '이와', '그의', '이의',
    '밝혔다', '전했다', '말했다', '보였다', '나타났다', '알려졌다', '됐다',
    '중인', '중이다', '한다', '된다', '보인다', '나온다',
    '경우', '부분', '정도', '이상', '이하', '사이',
}


def _validate_internal_links(content: str, valid_slugs: set) -> str:
    """Remove internal links whose slugs don't exist in the database."""
    def replace_link(match):
        slug = match.group(1)
        anchor_text = match.group(2)
        if slug in valid_slugs:
            return match.group(0)  # keep valid link
        logger.warning(f"Removing invalid internal link: /article/{slug}")
        return anchor_text  # replace with just the anchor text

    return re.sub(
        r'<a\s+href="/article/([^"]+)"[^>]*>(.*?)</a>',
        replace_link,
        content,
    )


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """Extract meaningful keywords from content, with 3x weight for H2/H3 headings."""
    # Extract heading text with 3x weight
    heading_texts = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', content, re.IGNORECASE)
    heading_clean = ' '.join(re.sub(r'<[^>]+>', '', h) for h in heading_texts)
    heading_words = re.findall(r'[\uAC00-\uD7A3]{2,}|[a-zA-Z]{4,}', heading_clean.lower())

    # Extract body text
    clean_text = re.sub(r'<[^>]+>', '', content)
    body_words = re.findall(r'[\uAC00-\uD7A3]{2,}|[a-zA-Z]{4,}', clean_text.lower())

    word_freq = {}
    for word in body_words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 1
    # Apply 3x weight for heading words
    for word in heading_words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 3

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]

    return keywords


VALID_CATEGORIES = [
    '경제', 'IT·테크', '글로벌 경제', '부동산', '연예', '스포츠',
]

# Unified editorial voice (no fake personas)
EDITORIAL_VOICE = (
    "당신은 NexusTopic 편집팀의 분석 기사를 작성합니다. "
    "AI를 활용한 데이터 기반 분석이며, 편집팀이 팩트체크와 최종 검토를 수행합니다. "
    "절대 1인칭(나, 저, 내가, 필자, 우리)을 사용하지 마세요. "
    "개인 의견이나 감정을 드러내지 말고, 데이터와 팩트로만 논지를 전개하세요. "
    "3인칭 객관적 서술만 사용하세요."
)


def _get_author_for_category(category: str) -> str:
    """Return the editorial team name."""
    return 'NexusTopic 편집팀'


ARTICLE_STRUCTURES = [
    # 구조 A: 탐사형 — "돈의 흐름을 따라가라"
    """기사는 탐사형(INVESTIGATIVE) 구조를 따르세요:
1. **핵심부터** — 다른 언론이 6번째 문단에 묻어둔 가장 중요한 팩트로 시작
2. **공식 발표 vs 현실** — 기업/당국의 공식 입장을 제시한 뒤 데이터로 반박
3. **돈의 흐름** — 누가 이익을 보는가? 구체적 금액, 시가총액, 매출액 제시
4. **역사적 선례** — 유사한 패턴의 과거 사례 분석. 당시 결과와 현재 시사점
5. **숨은 이해관계자** — 주류 언론이 놓치는 영향 받는 집단 분석
6. **결론** — 데이터를 바탕으로 명확한 분석 결론 도출. 애매한 표현 금지
7. **추적 지표** — 독자가 직접 추적할 수 있는 단일 핵심 지표 제시""",

    # 구조 B: 해설형 — "핵심 정리"
    """기사는 해설형(EXPLAINER) 구조를 따르세요:
1. **30초 요약** — 바쁜 독자가 캡처해서 공유할 수 있는 2-3문장 핵심 요약
2. **왜 중요한가** — 독자의 직장, 지갑, 일상에 미치는 구체적 영향
3. **여기까지의 경과** — 핵심 사건 3-5개를 타임라인(번호/불릿 리스트)으로 정리
4. **작동 원리** — 비유와 비교를 활용해 복잡한 내용을 쉽게 설명
5. **찬반 분석** — 실명 인물의 실제 입장을 인용하여 핵심 논쟁 정리
6. **향후 전망** — 2-3개 시나리오를 확률과 함께 제시 ("가능성 60%: ... 30%: ...")
7. **핵심 정리** — 한 문단, 하나의 명확한 결론""",

    # 구조 C: 반론형 — 통설에 도전
    """기사는 반론형(CONTRARIAN) 구조를 따르세요:
1. **통설 정리** — 이 주제에 대한 일반적 인식을 공정하게 2-3문장으로 제시
2. **균열 포인트** — 통설을 뒤흔드는 하나의 데이터, 트렌드, 간과된 사실 제시
3. **반론 구축** — 대안적 해석을 3개 이상의 데이터 포인트로 뒷받침. <strong>으로 핵심 수치 강조
4. **가장 강한 반박** — 해당 분석에 대한 가장 강력한 반론을 객관적으로 다루기
5. **검증 방법** — 언제, 어떤 지표로 이 분석의 적중 여부를 확인할 수 있는지 제시
6. **이미 움직이는 사람들** — 이 반론적 시각에 따라 행동하는 기업·투자자 소개
7. **시사점** — 이 분석이 시장·독자에게 의미하는 바를 구체적으로 정리""",

    # 구조 D: 심층분석형 — 인물, 기업, 기술 집중
    """기사는 심층분석형(DEEP-DIVE) 구조를 따르세요:
1. **결정적 순간** — 이야기의 본질을 담은 구체적 장면, 인용, 사건으로 시작
2. **배경 스토리** — 가장 중요한 2-3개의 결정이나 사건 중심으로 경과 정리
3. **숫자로 보기** — 최소 4-5개의 구체적 통계를 불릿 포인트나 비교로 시각적 제시
4. **경쟁 구도** — 핵심 플레이어 비교 (A사는 X, B사는 Y, 주인공은 Z)
5. **숨은 리스크** — 아무도 반영하지 않는 잠재적 위험 구체적 분석
6. **현장 시각** — 업계 내부자의 관점에서 바라본 인사이트
7. **12개월 전망** — 1년 후 이 이야기가 어떻게 될지 구체적이고 검증 가능한 예측""",
]


CATEGORY_TONE_GUIDE = {
    '경제': """카테고리별 톤 가이드 — 경제 (한경/매경/서울경제 스타일):
- 첫 문장: 핵심 결과 즉시 제시 ("코스피가 ~포인트 상승 마감했다")
- 둘째 문장: "~면서다" 또는 "~때문이다"로 원인 연결
- 수치는 소수점까지 정밀하게: "62.61포인트(1.14%)", "7186억원어치"
- 매수/매도 주체별(개인/기관/외국인) 금액 정리
- 종목별 등락은 짧게: "삼성전자도 2.83% 상승했다."
- 전문가 인용 시 실명+소속+직함 필수
- "~으로 풀이된다", "~것으로 분석된다"로 해석 삽입
- 건조하고 팩트 중심. 감정/비유 최소화
- 장중 흐름 서사: "장초반 강세 → 점심 전후 약보합 → 오후 반등" 식의 시간 흐름""",

    'IT·테크': """카테고리별 톤 가이드 — IT·테크 (전자신문/ZDNet 스타일):
- 첫 문장: 주체+핵심 행동 압축 ("삼성전자 DS부문이 영업이익률 50%를 목표로 포트폴리오를 재구성한다")
- 기술 용어는 약어(풀네임) 형태: "HBM(고대역폭메모리)", "TGV(유리 관통 전극)"
- 인물 소개: 학력→경력→현직 순으로 한 문장 압축 + 직함 사용 ("~대표", "~전무")
- 기업 간 수치 대비: "삼성 영업이익률 37.27%, SK하이닉스 58.39%"
- 중간에 기자 평가 삽입: "상당히 이례적인 시도다", "업계에서는 주목하고 있다"
- 익명 소스: "사안에 밝은 업계 관계자는" 패턴
- 당사자 직접 인용(큰따옴표)으로 마무리
- [단독], [현장] 같은 태그는 사용하지 않아도 됨""",

    '글로벌 경제': """카테고리별 톤 가이드 — 글로벌 경제 (연합인포맥스/한경 글로벌 스타일):
- 오프닝: 글로벌 시장의 큰 그림 한 문장 → 핵심 변수/이슈
- 글로벌 IB 2~3곳의 구체적 전망치 인용 (팩트셋, 모건스탠리, 골드만삭스 등 기관명+수치)
- 섹터별 소제목으로 구분 ("IT 업종의 강세", "산업재의 낙수효과" 등)
- 영문 용어는 영문 그대로: S&P500, EPS, Fed, FOMC, CPI
- 각 섹터마다 대표 기업 1~2곳의 구체적 실적 예시
- 마지막에 한국 투자자 관점의 시사점 반드시 포함
- "~전망이다", "~것으로 분석된다" 어미 활용""",

    '부동산': """카테고리별 톤 가이드 — 부동산 (머니투데이/한경 부동산 스타일):
- 제목은 구어체/감성적 가능: "여보, 현금 8억 있어?" 식
- 오프닝: 실수요자/예비 청약자 관점의 시장 분위기 묘사
- 단지 소개 시: 시공사명+위치+총가구+일반분양수+입지 특징 반드시 포함
- 전용면적은 "전용 84㎡" 형태, 가격은 "3.3㎡당 ~만원" 형태
- 정책 변수 반드시 언급: 양도세, 대출규제(DSR/LTV), 공시가격, 현실화율
- 양극화 프레이밍: 강남 vs 지방, 서울 vs 수도권
- 독자를 '실수요자', '예비 청약자'로 지칭
- "~것으로 풀이된다", "~것으로 분석된다" 어미
- 마무리: 전문가 조언 (구체적 행동 가이드)""",

    '연예': """카테고리별 톤 가이드 — 연예 (OSEN/스포츠조선 스타일):
- 중요: 연예 기사는 경제 분석이 아니다. 콘텐츠와 사람 이야기가 중심
- 첫 문장: "그룹 XX 출신 [인물]이(가) [화제 포인트]로 시선을 집중시켰다"
- 출처 명시: "X일 방송된 [채널] '[프로그램명]'에서는" 또는 "자신의 SNS에"
- 관용구 활용: "시선을 모았다", "화제다", "눈길을 끌었다"
- 외모/패션/퍼포먼스 묘사 포함
- 방송 대사나 SNS 원문 직접 인용(큰따옴표)
- 프로그램명은 작은따옴표: '나는 솔로', '더 글로리'
- 마지막 문단: 과거 이력 또는 앞으로의 활동 계획
- 해라체이나 경제 기사보다 묘사적/서사적
- 절대 비즈니스/경제 프레임으로 쓰지 말 것""",

    '스포츠': """카테고리별 톤 가이드 — 스포츠 (스포츠동아/일간스포츠 스타일):
- 중요: 스포츠 기사는 경제 분석이 아니다. 경기와 선수가 중심
- 경기 프리뷰: 긴장감 조성으로 시작 ("반드시 넘어야 한다", "벼랑 끝에 몰린")
- 경기 정보: 날짜+시간+구장+대진 반드시 명시
- 선수 성적: "타율 0.333(12타수 4안타) 2홈런 2타점" 식으로 정밀 표기
- 선수 이력: KBO/K리그 소속팀, 시즌 성적, 한국 경력 상세히 (한국 독자 친숙도 활용)
- 선수 직접 인용 1~2개 포함
- 규정/룰 변경은 구체적 수치와 함께 설명
- 역사적 통계: "역대 ~은 총 N차례"
- 드라마틱 표현 적극 활용: "벼랑 끝", "막을 올린다", "출사표를 던졌다", "승부수"
- 절대 '단순한 X가 아니다' 패턴 금지
- 절대 모든 스포츠를 경제/비즈니스/데이터 프레임으로 쓰지 말 것""",
}


def _build_prompt(
    topic: str,
    min_words: int,
    max_words: int,
    target_audience: str,
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
    search_context: dict = None,
    financial_context: str = None,
    category: str = None,
    news_context: str = None,
) -> str:
    """Build the article generation prompt."""
    # Randomly select article structure for variety
    structure_block = random.choice(ARTICLE_STRUCTURES)

    # Build internal links section
    internal_links_section = ""  # 내부 링크 비활성화

    # Build source reference section
    source_section = ""
    if source_url:
        source_section = f"""
출처 참고:
이 트렌딩 토픽의 원문 출처: {source_url}
적절한 곳에서 <a href="{source_url}" target="_blank" rel="noopener noreferrer">출처 텍스트</a>로 참조하세요.
"""

    # External links section — fact-based sourcing
    external_links_section = """
출처 및 외부 링크 (신뢰도 핵심 — 모든 주장에 근거 필수):
본문 내에 4-6개의 검증 가능한 출처 링크를 자연스럽게 삽입하세요.
HTML 앵커 태그 사용: <a href="URL" target="_blank" rel="noopener noreferrer">설명 텍스트</a>

출처 유형 (우선순위):
1. 공식 기관 데이터: 한국은행(bok.or.kr), 통계청(kostat.go.kr), 금융감독원(fss.or.kr), 기획재정부(moef.go.kr)
2. 주요 언론 보도: 한국경제(hankyung.com), 매일경제(mk.co.kr), 연합뉴스(yna.co.kr) — 가능하면 구체적 기사 경로 포함
3. 글로벌 출처: Reuters, Bloomberg, IMF, World Bank — 구체적 보고서/기사 경로 포함
4. 위키백과: 배경 설명, 정의, 역사적 맥락에만 사용 (주요 출처로 쓰지 말 것)

출처 규칙 (필수):
- 모든 통계/수치에 반드시 출처(기관명 + 연도)를 밝힐 것: "한국은행에 따르면(2026년 1분기 기준)", "통계청 발표(2025년)"
- 홈페이지(예: reuters.com/)만 링크하지 말 것 — 가능하면 구체적 기사/보고서/데이터 페이지를 링크
- URL을 추측하거나 조작하지 말 것 — 확실한 URL만 사용하고, 불확실하면 기관 홈페이지 + 보고서명을 텍스트로 명시
- 문장에 자연스럽게 녹여서 삽입

기사 하단에 반드시 "Sources & References" 섹션을 추가하세요:
<div class="article-sources">
<h3>출처 및 참고자료</h3>
<ul>
기사에서 인용한 모든 출처를 [기관명 — 보고서/기사 제목 (연도)] 형식으로 나열
</ul>
</div>
"""

    # Build real search data section
    search_data_section = ""
    if search_context:
        parts = []
        ac = search_context.get('autocomplete', [])
        if ac:
            ac_lines = "\n".join(f'  - "{q}"' for q in ac[:15])
            parts.append(f"Google 자동완성 제안 (실제 검색어):\n{ac_lines}")
        top = search_context.get('related_top', [])
        if top:
            top_lines = "\n".join(f'  - "{q}"' for q in top[:10])
            parts.append(f"상위 관련 검색어 (Google Trends):\n{top_lines}")
        rising = search_context.get('related_rising', [])
        if rising:
            rising_lines = "\n".join(f'  - "{q}"' for q in rising[:10])
            parts.append(f"급상승 검색어 (관심도 급증):\n{rising_lines}")
        if parts:
            search_data_section = f"""
실제 검색 데이터 (실제 검색 행동에 맞게 최적화하세요):
{chr(10).join(parts)}

활용 방법:
- 이 실제 검색어 중 2개 이상을 H2 제목으로 활용 (자연스럽게 변형)
- 관련 키워드를 본문에 자연스럽게 녹이기
"""

    # Editorial voice (unified, no fake personas)
    persona_voice = EDITORIAL_VOICE

    # Category-specific tone guide
    category_guide = CATEGORY_TONE_GUIDE.get(category or '', '')
    category_guide_section = f"\n{category_guide}\n" if category_guide else ""

    today = datetime.now().strftime('%Y년 %m월 %d일')

    return f"""다음 트렌딩 토픽에 대해 기사를 한국어로 작성하세요: {topic}

오늘 날짜: {today}
현재 연도: {today[:5]}

날짜 인지 및 검증 프로세스 (모든 기사 작성의 전제 조건):
1단계 — 날짜 인지: 오늘은 {today}이다. 이 날짜를 기준으로 모든 판단을 내려야 한다.
2단계 — RSS/토픽 검증: 아래 제공된 토픽이 {today} 기준으로 유효한 이슈인지 확인한다.
  - 이미 종료된 이벤트를 마치 예정인 것처럼 쓰지 말 것 (예: 이미 열린 GTC를 "예정"이라 쓰지 말 것)
  - 이미 시행된 정책을 "시행 예정"이라 쓰지 말 것
  - RSS에서 가져온 토픽이 며칠 전 뉴스라면, {today} 기준 후속 진전이 있는지 확인
3단계 — 수치 시점 확인: 기사에 사용하는 모든 수치가 언제 기준인지 명확히 한다.
  - "시가총액 3조 달러" → 이게 오늘 기준인지, 1년 전 기준인지 반드시 확인
  - "육아휴직 급여 월 150만원" → 이게 현행인지, 구법인지 반드시 확인
  - 확인 불가하면 "~년 기준", "약" 등 헤지 표현 필수
4단계 — 최종 검수: 기사 완성 후 모든 연도/날짜/수치를 {today} 기준으로 재확인한다.

사실 정확성 규칙 (위반 시 기사 거절):
- 모든 가격, 통계, 날짜, 사실관계는 {today} 기준 정확해야 합니다.
- 학습 데이터의 오래된 가격/통계에 의존하지 마세요.
- 특정 수치(가격, 시가총액, 사용자 수 등)의 현재 정확성이 불확실하면 "약", "{today[:5]} 기준", "약 X원" 등 헤지 표현 사용 — 오래된 수치를 현재 사실처럼 쓰지 마세요.
- 아래에 실시간 금융 데이터가 제공되면, 환율·주가·원자재 가격은 반드시 해당 수치를 사용하세요.

작성 주체:
{persona_voice}
기사 하단에 "이 기사는 AI 분석을 기반으로 작성되었으며, NexusTopic 편집팀이 검토했습니다."를 <p class="ai-disclosure"> 태그로 포함하세요.

한국 25-45세 성인 독자를 위해 씁니다. 카테고리에 맞는 톤으로 작성하세요 — 모든 기사를 경제/투자/코스피와 연결할 필요 없습니다.
{category_guide_section}

핵심 원칙 — 팩트와 출처가 생명이다:
- 모든 주장, 통계, 예측에 반드시 출처를 밝힐 것 (기관명 + 연도)
- 근거 없는 단정적 예측 절대 금지: "~할 것이다", "~% 폭락할 것" → 대신 "분석가들은 ~로 예상", "~할 가능성이 있다", "~할 수 있다" 사용
- 미래 전망은 반드시 불확실성 표현과 함께: "~에 따르면", "시장에서는 ~로 보고 있다"
- 가상의 인용("한 전문가는 ~라고 말했다")을 만들어내지 말 것 — 실제 보도된 인용만 사용
- 하나의 기사에 서로 관련 없는 이슈를 억지로 엮지 말 것 — 주제 하나에 집중

글쓰기 품질 원칙:
- 완벽하게 정돈된 글보다는 숙련된 기자가 빠르게 써내린 듯한 자연스러움을 추구
- 모든 소제목을 병렬 구조로 맞추지 말 것 — 소제목 형식을 의도적으로 다양하게 (질문형, 명사형, 서술형 섞기)
- 문단 길이도 일정하지 않게 — 짧은 한 문장 문단과 3~4문장 문단을 자유롭게 배치
- 핵심 인사이트는 "정리하면" "요약하면" 대신 자연스러운 흐름 속에서 전달
- "첫째, 둘째, 셋째" 나열식 전개를 한 기사에서 2회 이상 반복하지 말 것

글쓰기 핵심 규칙:
- 문체: 반드시 해라체(~다, ~이다, ~했다, ~된다)로 통일. 합쇼체(~습니다, ~합니다) 절대 금지. 경제지 기사 문체.
- 절대 "~에 나섰다", "~이 화두다", "~이 주목받고 있다"로 시작하지 마세요
- 금지 표현: "귀추가 주목된다", "지켜봐야 할 것이다", "결론적으로", "주목할 만하다", "패러다임", "게임체인저", "심층적으로", "다각적으로", "~할 것으로 보인다"만 반복
- 절대 1인칭(나, 저, 내가, 필자, 우리) 사용 금지. 3인칭 객관적 서술만 사용
- 감정적/선정적 표현 금지: "충격적", "놀라운", "불편한 진실", "축배를 들기엔" 등
- 문장 길이를 자연스럽게 변화: 짧은 문장과 긴 분석 문장을 섞기
- 구체적 숫자, 날짜, 퍼센트, 금액을 가능한 한 포함
- 데이터와 팩트 중심으로 논지를 전개하되, 분석적 시각은 유지
- AI가 쓴 듯한 완벽한 병렬 구조 피하기

기사 요구사항:
- 대상 독자: {target_audience}
- 분량: 되도록 1500어절 이상, 최소 1200어절은 반드시 넘길 것. 목표는 {min_words}-{max_words}어절.
- 형식: HTML 시맨틱 태그 (h2, h3, p, ul, ol, strong, em, blockquote)
- 기사 구조: 최소 H2 4개 이상 (배경/현황 → 데이터 분석 → 이해관계자/영향 → 전망)
- 데이터 시각화: 가능하면 비교 테이블(<table>) 또는 핵심 수치 리스트를 1개 이상 포함
- 톤: 전문적이고 객관적 — 카테고리별 톤 가이드 참조
- SEO: 관련 키워드 자연스럽게 포함
{internal_links_section}{external_links_section}{source_section}{search_data_section}{financial_context or ''}{news_context or ''}
제목 최적화 (검색 노출 핵심):
- 필수: H2 제목 중 최소 2개는 질문형(?로 끝남). 이것은 필수 요건.
  * 실제 검색 데이터가 있으면 실제 검색어를 H2 질문 제목으로 변환
  * 형식 예: "코스피 전망은?", "왜 금리가 오르나?", "반도체 투자 지금 해도 될까?"
  * 질문형 제목은 Google '관련 질문' 박스 노출에 유리
- 나머지 H2/H3 제목에도 관련 키워드 자연스럽게 포함

{structure_block}

스타일 가이드:
- 데이터와 팩트 중심의 분석 기사 — 주관적 의견이나 1인칭 표현 금지
- 긴 문단 금지: 2-3문장 최대
- 데이터를 자연스럽게 녹이기: "전년 대비 47% 급등은 단순히 인상적인 수준이 아니다 — 이 업종에서 전례 없는 수치다"
- 비유와 비교로 복잡한 주제를 접근 가능하게
- 결론은 데이터에 근거한 전망 제시 — "지켜봐야 할 것이다" 같은 애매한 결말 금지
- 중요: "에디터 의견:", "전망:" 같은 라벨 사용 금지 — 분석을 본문에 자연스럽게 녹이기
- 미래 전망은 반드시 조건부로: "~한다면 ~할 수 있다", "~기관은 ~로 전망했다"

최신성 원칙 (AI 학습 데이터는 과거다 — 반드시 최신 정보 확인):
- 기사 작성 전 반드시 해당 토픽의 최신 뉴스/데이터를 웹 검색으로 확인할 것
- 다른 언론사(한경, 매경, 연합뉴스, MBC, SBS 등)가 같은 토픽으로 어떻게 보도했는지 참조할 것
- 같은 토픽을 다룬 언론사 기사 최소 3개 이상 참조 후 작성
- 수치, 날짜, 정책, 이벤트는 반드시 현재 연도 기준 최신 데이터를 사용
- AI 모델의 학습 데이터 기준 과거 수치를 현재 사실처럼 서술하지 말 것
- 실제 언론사 기사의 구성, 톤, 데이터 활용 방식을 참고해서 동일한 수준의 기사를 작성

실제 언론사 수준 기사 작성 원칙 (가장 중요 — 이 기사가 한경/매경/MBC에 실려도 위화감 없어야 함):
- "왜 지금 이 이슈인가?"에 반드시 답할 것 — 핵심 트리거(법 개정, 정책 변경, 실적 발표, 특정 사건)를 반드시 포함
  * 나쁜 예: "강남 아파트가 떨어지고 있다" (원인 없음)
  * 좋은 예: "양도세 중과 유예 5월 종료를 앞두고 절세 급매가 쏟아지면서 강남 3구 낙폭이 확대됐다"
- 구체적 수치 밀도를 실제 언론사 수준으로 유지: 주간 변동률, 전년 대비 증감, 개별 기업/지역 수치
- 정책/제도 변경사항은 반드시 최신 기준 적용 — 예: 육아휴직 급여, DSR 규제, 세율 등은 매년 바뀜
- 시가총액, 매출, 주가 등 빠르게 변하는 수치는 반드시 최신 실적 발표 기준으로 사용
- 컨퍼런스/이벤트(GTC, CES, MWC 등)는 반드시 현재 연도 행사 기준으로 작성
- 관련 법안 통과, 정부 발표, 규제 변경 등 최근 6개월 이내 주요 변화를 반드시 반영

수치 교차 검증 원칙 (수학적 정합성 필수):
- 퍼센트와 절대값을 함께 쓸 때 계산이 맞는지 반드시 확인 — (변동값/기준값) × 100 = 퍼센트
  * 나쁜 예: "5,730건에서 14,866건으로 45.7% 급증" (실제로는 159% 증가)
  * 좋은 예: "5,730건에서 14,866건으로 약 2.6배 급증" 또는 정확한 퍼센트 사용
- A에서 B로 변할 때: 증가율 = (B-A)/A × 100
- 서로 다른 출처의 수치를 하나의 문장에 섞지 말 것 — 출처가 다르면 시점/기준이 다를 수 있음
- 비율, 점유율 등이 합산 100%를 넘지 않는지 확인
- "전년 대비", "전월 대비", "전주 대비" 등 비교 기준 시점을 명확히 표기

사실 확인 원칙 (위반 시 기사 전체가 무가치해짐 — 최우선 준수):
- 개인 이름을 절대 사용하지 말 것. 전문가, 애널리스트, 교수, CEO 등 어떤 인물의 이름도 기사에 넣지 마세요.
  * "업계 관계자는", "한 증권사 애널리스트는", "현지 매체에 따르면" 등 익명 표현만 사용
  * "김XX 교수", "박XX 연구원" 같은 형태도 금지 — 이름 자체를 쓰지 마세요
  * 유일한 예외: 대통령, 장관 등 공직자 또는 기업 CEO처럼 누구나 아는 공인만 실명 사용 가능
- 확인되지 않은 수치, 인용, 투자 금액을 절대 만들어내지 말 것
- 직접 인용문("..."이라고 말했다)은 실제 보도된 것만 사용 — 인용문을 만들어내지 말 것
- "~억 원 투자", "~% 증가" 같은 구체적 수치는 실제 데이터만 사용
- 확인 불가한 정보는 생략하거나 "보도에 따르면", "시장에서는 ~로 추정" 등 출처 명시
- 금리, 환율, 주가, 물가 등 거시경제 수치는 반드시 아래 제공된 실시간 금융 데이터 기준으로 작성
- 실시간 데이터가 없는 수치는 "약", "추정", "~년 기준" 등 헤지 표현 필수
- 실제 사건이나 발표가 아닌 추측성 시나리오를 사실처럼 서술 금지
- 현실과 정반대되는 주장 금지 (예: 실적 호조인데 "실적 쇼크" 제목 금지)
- 정부 정책(세율, 급여, 대출규제 등)은 반드시 현행 기준으로 작성 — 과거 기준 인용 시 연도를 명시해야 함
- 기업 실적/시가총액은 가장 최근 분기 발표 기준 사용 — 1년 전 수치를 현재처럼 쓰지 말 것

FAQ 섹션은 작성하지 마세요. 본문만 작성하세요.

형식: HTML만 (h2, h3, p, ul, ol, strong, em, blockquote). <html>/<head>/<body> 태그 없음.

추가 제공:
- 제목 (한국어 40자 이내) — 검색 순위 + 클릭률 모두 최적화
  제목 규칙:
  * 핵심 키워드를 제목 앞 3-4어절에 배치
  * 파워 워드는 최대 1개 ("긴급", "확인됨") — 과용 금지
  * 검색 의도에 맞으면 질문형 사용: "왜 코스피가 하락했나?"
  * 구체적 정보 포함: 이름, 숫자, 날짜 — 막연한 제목 금지
  * 좋은 예: "삼성전자 반도체 매출 40% 급감, 원인은?", "코스피 2400선 붕괴, 투자 전략은?"
  * 나쁜 예: "AI의 미래를 탐구하다", "충격적인 경제 변화"

- 메타 설명 (한국어 80자 이내 엄수):
  * 이 주제에 대한 가장 흔한 검색 의도에 답하는 한 문장
  * 관련 키워드 2-3개 자연스럽게 포함
  * 능동태, 구체적 숫자/사실
  * 80자 이내 (공백·구두점 포함)

- 카테고리: 아래 9개 중 기사 내용에 가장 맞는 것을 선택 (RSS 소스 카테고리와 다를 수 있음 — 반드시 내용 기준으로 판단)
  * 경제: 한국 국내 경제/기업/시장 (코스피, 한국은행, 국내 기업 실적)
  * IT·테크: 기술/반도체/AI/소프트웨어/하드웨어/스타트업 (순수 기술 주제만)
  * 글로벌 경제: 해외 경제 (미국 증시, 연준, 달러, 유가, 비트코인, 해외 기업)
  * 정치: 국회/대통령/여야/선거/외교/안보
  * 사회: 한국 국내 사건·사고/교육/환경/노동/의료정책/법원/복지 (정부 의료정책, 식약처 → 사회)
  * 글로벌 사회: 해외 사건/국제기구/기후변화/해외 사회 이슈
  * 부동산: 아파트/전세/분양/청약/재건축
  * 연예: K-POP/드라마/영화/OTT/연예인
  * 스포츠: KBO/K리그/MLB/NBA/올림픽/선수

- 해시태그: 기사를 읽은 후 핵심 주제를 대표하는 고유명사/핵심 키워드 정확히 3개 (쉼표 구분)
  * 반드시 고유명사 또는 핵심 주제어만 사용 (예: 삼성전자, 반도체, AI)
  * 절대 금지: 동사(있다, 하다), 형용사(단순한, 새로운), 조사(에서, 으로), 부사(달러는, 매우)
  * 좋은 예: "비트코인, 암호화폐, 가상자산" / "코스피, 외국인매수, 이란"
  * 나쁜 예: "있다, 단순한, 인플레이션" / "기름값, 상한제, 인가"

응답 형식 (각 항목을 반드시 별도 줄에 작성):
TITLE: [제목]
META: [메타 설명]
CATEGORY: [카테고리]
TAGS: [태그1, 태그2, 태그3]
CONTENT:
[HTML 콘텐츠]
"""


def _parse_response(response_text: str, topic: str) -> Dict:
    """Parse LLM response into article dictionary.

    Handles both multi-line and single-line formats:
      Multi-line: TITLE: ...\nMETA: ...\nCATEGORY: ...\nCONTENT:\n...
      Single-line: TITLE: ... META: ... CATEGORY: ... CONTENT: ...
      No CONTENT label: TITLE: ... META: ... CATEGORY: ...\n<h2>...
    """
    # Try extracting TITLE — stop at newline, META, or CATEGORY
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|(?=\s*META:)|(?=\s*CATEGORY:))', response_text, re.IGNORECASE)
    # Try extracting META — stop at newline, CATEGORY, or CONTENT
    meta_match = re.search(r'META:\s*(.+?)(?:\n|(?=\s*CATEGORY:)|(?=\s*CONTENT:))', response_text, re.IGNORECASE)
    # Try extracting CATEGORY — stop at newline, TAGS, CONTENT, or first HTML tag
    category_match = re.search(r'CATEGORY:\s*(.+?)(?:\n|(?=\s*TAGS:)|(?=\s*CONTENT:)|(?=\s*<))', response_text, re.IGNORECASE)
    # Try extracting TAGS — stop at newline, CONTENT, or first HTML tag
    tags_match = re.search(r'TAGS:\s*(.+?)(?:\n|(?=\s*CONTENT:)|(?=\s*<))', response_text, re.IGNORECASE)
    # Try extracting CONTENT — with or without the CONTENT: label
    content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.IGNORECASE | re.DOTALL)

    # Fallback: if no CONTENT: label, grab everything after the last metadata field
    last_meta_end = max(
        (m.end() for m in [category_match, tags_match, meta_match] if m),
        default=0,
    )
    if not content_match and last_meta_end > 0:
        after_category = response_text[last_meta_end:]
        # Find first HTML tag as content start
        html_start = re.search(r'<(?:h[1-6]|p|div|section|ul|ol|blockquote)', after_category, re.IGNORECASE)
        if html_start:
            content_match_text = after_category[html_start.start():].strip()
        else:
            content_match_text = after_category.strip()
    else:
        content_match_text = None

    if not all([title_match, meta_match]) or (not content_match and not content_match_text):
        logger.error("Failed to parse response properly")
        # Last resort: strip any TITLE/META/CATEGORY prefix from content
        content = re.sub(r'^TITLE:.*?(?=<)', '', response_text, flags=re.IGNORECASE | re.DOTALL).strip()
        title = topic
        meta_description = f"{topic}에 대한 심층 분석"
    else:
        title = title_match.group(1).strip().rstrip('.')
        meta_description = meta_match.group(1).strip().rstrip('.')
        content = content_match.group(1).strip() if content_match else content_match_text

    category = 'IT·테크'
    if category_match:
        raw_category = category_match.group(1).strip()
        if raw_category in VALID_CATEGORIES:
            category = raw_category
        else:
            logger.warning(f"Invalid category '{raw_category}', defaulting to IT·테크")

    # Clean up code block wrappers (```html ... ```) that Gemini sometimes adds
    content = re.sub(r'```html\s*', '', content)
    content = re.sub(r'```\s*$', '', content)
    content = content.strip()

    word_count = len(re.sub(r'<[^>]+>', '', content).split())
    reading_time = calculate_reading_time(content)

    # Use AI-generated tags if available, fallback to frequency-based extraction
    if tags_match:
        raw_tags = tags_match.group(1).strip().strip('[]')
        keywords = [t.strip() for t in raw_tags.split(',') if len(t.strip()) >= 2]
        logger.info(f"Using AI-generated tags: {keywords}")
    else:
        keywords = extract_keywords(content)

    return {
        'title': title,
        'meta_description': meta_description,
        'content': content,
        'keywords': keywords,
        'reading_time': reading_time,
        'word_count': word_count,
        'timestamp': datetime.now().isoformat(),
        'topic': category,
        'trending_keyword': topic,
    }


def generate_article(
    topic: str,
    min_words: int = 500,
    max_words: int = 700,
    target_audience: str = "한국 25-45세 성인 독자",
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
    search_context: dict = None,
    financial_context: str = None,
    news_context: str = None,
    **kwargs,
) -> Dict:
    """
    Generate a complete SEO-optimized article.
    Primary: Gemini 3.1 Pro Preview via CLI
    Fallback: Gemini API (gemini-3.1-pro-preview)
    """
    # Randomize word count target within the given range for natural variation
    target = random.randint(min_words, max_words)
    # Set effective min to ~70% of target, effective max to target
    effective_min = max(min_words, int(target * 0.7))
    effective_max = target

    logger.info(f"Generating article about: {topic}")
    logger.info(f"Target length: {effective_min}-{effective_max} words (from range {min_words}-{max_words})")

    prompt = _build_prompt(
        topic, effective_min, effective_max, target_audience,
        existing_articles=existing_articles,
        source_url=source_url,
        author_name=author_name,
        search_context=search_context,
        financial_context=financial_context,
        category=kwargs.get('category'),
        news_context=news_context,
    )

    # Collect valid slugs for internal link validation
    valid_slugs = set()
    if existing_articles:
        valid_slugs = {a['slug'] for a in existing_articles if a.get('slug')}

    def _try_generate(provider_name, generate_fn):
        """Generate once. 500+ words = accept, under 500 = discard."""
        response_text = generate_fn()
        article = _parse_response(response_text, topic)
        if valid_slugs and article.get('content'):
            article['content'] = _validate_internal_links(article['content'], valid_slugs)
        wc = article.get('word_count', 0)
        logger.info(f"[{provider_name}] Generated: {article.get('title', '?')} ({wc} words)")
        return article

    # Primary: Gemini API with Google Search grounding (ensures real-time data)
    if os.getenv('GOOGLE_API_KEY') and genai:
        logger.info(f"  Model: gemini-3.1-pro-preview (API + Google Search grounding)")
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 30 * attempt
                    logger.info(f"Rate limit retry {attempt}/3, waiting {wait}s...")
                    time.sleep(wait)
                article = _try_generate(
                    'Gemini API+Search',
                    lambda: _generate_with_gemini_api(prompt, use_search=True),
                )
                if article:
                    article['_provider'] = 'gemini-3.1-pro-preview (API+Search)'
                    time.sleep(5)
                    return article
            except Exception as e:
                if '429' in str(e) or 'quota' in str(e).lower() or 'rate' in str(e).lower():
                    logger.warning(f"Gemini API rate limit hit (attempt {attempt+1}/3)")
                    continue
                logger.error(f"Gemini API error: {e}")
                break
        logger.warning("Gemini API exhausted, falling back to CLI")

    # Fallback: Gemini CLI (no grounding — last resort)
    if _gemini_cli_path:
        try:
            logger.info(f"  Model: gemini-3.1-pro-preview (CLI, no grounding)")
            article = _try_generate('Gemini CLI', lambda: _generate_with_gemini_cli(prompt))
            if article:
                article['_provider'] = 'gemini-3.1-pro-preview (CLI)'
                return article
        except Exception as e:
            logger.warning(f"Gemini CLI failed: {e}")

    logger.error("No LLM provider available (Gemini CLI and Gemini API both failed).")
    return {}


def _factcheck_and_fix_with_claude(article: Dict) -> Dict:
    """
    Claude Haiku로 기사 팩트체크 + 할루시네이션 수정.
    - 가상 인물/기업 → 익명 표현으로 교체
    - 잘못된 수치 → 제거 또는 헤지 표현으로 교체
    - 존재하지 않는 제품/기능 → 제거
    수정된 article dict를 반환.
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key or not anthropic:
        logger.warning("Claude API not available, skipping factcheck")
        return article

    title = article.get('title', '')
    content = article.get('content', '')
    if not content:
        return article

    prompt = f"""다음 한국어 뉴스 기사를 팩트체크하고 문제가 있으면 수정해주세요.

제목: {title}

본문 (HTML):
{content}

검수 규칙 (모든 항목을 빠짐없이 체크할 것):

[할루시네이션]
1. 가상 인물: 실존 확인이 안 되는 인물 이름 → "업계 관계자는", "한 애널리스트는" 등 익명 표현으로 교체. 대통령/장관/유명 CEO 등 공인만 실명 유지.
2. 가상 기업/기관: 실존하지 않는 회사명, 연구소명 → 제거하거나 "한 기업", "관련 업체" 등으로 교체
3. 존재하지 않는 제품/기능/칩셋/모델명 → 해당 문장 제거
4. 잘못된 수치: 가격, 시세, 환율, 지수 등이 현실과 동떨어져 있으면 → 제거하거나 "약 ~원대" 헤지 표현으로 교체

[스펠링/표기]
5. 영문 고유명사 스펠링 오류 → 올바른 스펠링으로 수정 (예: OpenClo → OpenClaw, Ndivia → Nvidia)
6. 한글 외래어 표기 오류 → 통용 표기로 수정

[글 완결성]
7. 글이 중간에 끊겼는지 확인: 마지막 문장이 완결되지 않았거나, HTML 태그가 닫히지 않은 경우 → 자연스럽게 마무리 문장을 추가하고 태그를 닫아줄 것
8. 마지막 문단이 결론 없이 끝나면 → 1~2문장으로 자연스럽게 마무리

[카테고리]
9. 기사 내용에 맞는 카테고리 판단:
   - 경제: 한국 국내 경제/기업/시장
   - 글로벌 경제: 해외 경제/미국증시/달러/유가/비트코인/해외기업
   - IT·테크: 순수 기술 주제 (반도체/AI/소프트웨어/신제품)
   - 정치: 국회/대통령/여야/선거/외교/안보
   - 사회: 한국 사건사고/교육/환경/의료정책
   - 글로벌 사회: 해외 사건/국제기구/기후변화
   - 부동산/연예/스포츠

[억지 연결]
10. 서로 관계없는 주제가 억지로 엮여있으면 관련 없는 부분 제거 (예: 운전면허+코스피, 에어팟+환율)

[내부 링크]
11. 본문에 <a href="/article/..."> 형태의 내부 링크가 있으면 모두 제거 (링크 텍스트는 유지, <a> 태그만 제거)

[코드/포맷 오류]
12. 본문에 ```html, ```, 마크다운 코드블록 래퍼가 있으면 제거. HTML 본문만 남길 것

응답 형식 (반드시 지킬 것):
TITLE: 수정된 제목 (수정 불필요하면 원본 그대로)
CATEGORY: 카테고리
ISSUES: 발견된 문제 요약 (없으면 "없음")
CONTENT:
수정된 HTML 본문 (수정 불필요하면 원본 그대로. 반드시 완결된 글이어야 함)"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        logger.info(f"  Claude factcheck response length: {len(raw)}")

        # Parse response
        title_match = re.search(r'TITLE:\s*(.+?)(?:\n|$)', raw)
        cat_match = re.search(r'CATEGORY:\s*(.+?)(?:\n|$)', raw)
        issues_match = re.search(r'ISSUES:\s*(.+?)(?:\nCONTENT:|\n\n)', raw, re.DOTALL)
        content_match = re.search(r'CONTENT:\s*\n(.+)', raw, re.DOTALL)

        issues = issues_match.group(1).strip() if issues_match else '파싱 실패'
        logger.info(f"  Claude issues: {issues[:100]}")

        if issues.strip() == '없음':
            logger.info(f"  Claude: No issues found, keeping original")
            # Still update category if Claude suggests different
            if cat_match:
                new_cat = cat_match.group(1).strip()
                for valid_cat in ['경제', 'IT·테크', '글로벌 경제', '정치', '사회', '글로벌 사회', '부동산', '연예', '스포츠']:
                    if valid_cat in new_cat:
                        article['topic'] = valid_cat
                        break
            return article

        # Apply fixes
        if title_match:
            new_title = title_match.group(1).strip()
            if new_title and new_title != title:
                logger.info(f"  Claude fixed title: {title[:30]} → {new_title[:30]}")
                article['title'] = new_title

        if cat_match:
            new_cat = cat_match.group(1).strip()
            for valid_cat in ['경제', 'IT·테크', '글로벌 경제', '정치', '사회', '글로벌 사회', '부동산', '연예', '스포츠']:
                if valid_cat in new_cat:
                    if valid_cat != article.get('topic'):
                        logger.info(f"  Claude fixed category: {article.get('topic')} → {valid_cat}")
                    article['topic'] = valid_cat
                    break

        if content_match:
            new_content = content_match.group(1).strip()
            if new_content and len(new_content) > 200:
                article['content'] = new_content
                article['word_count'] = len(re.sub(r'<[^>]+>', '', new_content).split())
                logger.info(f"  Claude fixed content ({article['word_count']} words)")

        article['_factchecked'] = True
        return article

    except Exception as e:
        logger.warning(f"  Claude factcheck failed: {e}")
        return article


def generate_multiple_articles(
    topics: list,
    articles_count: int = 3,
    **kwargs
) -> list:
    """Generate multiple articles from a list of topics with duplicate checking."""
    logger.info(f"Generating {articles_count} articles from {len(topics)} topics")

    # Get existing articles and trending keywords to avoid duplicates
    existing_titles = set()
    existing_keywords = set()
    existing_articles_for_links = []  # For internal linking in prompts
    try:
        from scripts.database import get_db_client, is_supabase_enabled
        if is_supabase_enabled():
            db = get_db_client()
            existing_articles = db.list_articles(limit=100, published_only=False)
            existing_articles_for_links = [
                {'title': a.get('title', ''), 'slug': a.get('slug', ''), 'topic': a.get('topic', '')}
                for a in existing_articles if a.get('slug')
            ]
            existing_titles = {a.get('title', '').lower() for a in existing_articles}
            logger.info(f"Loaded {len(existing_titles)} existing article titles for duplicate check")

            db_keywords = db.list_trending_keywords(limit=200)
            existing_keywords = {k.lower() for k in db_keywords}
            logger.info(f"Loaded {len(existing_keywords)} existing trending keywords for duplicate check")
    except Exception as e:
        logger.warning(f"Could not load existing articles: {str(e)}")

    # Also load from local JSON index for fallback duplicate check
    try:
        import json
        from pathlib import Path
        index_path = Path(__file__).parent.parent.parent / 'frontend' / 'public' / 'articles' / 'index.json'
        if index_path.exists():
            with open(index_path, 'r') as f:
                local_articles = json.load(f)
            for a in local_articles:
                existing_titles.add(a.get('title', '').lower())
            logger.info(f"Loaded {len(local_articles)} local article titles for duplicate check")
    except Exception as e:
        logger.warning(f"Could not load local articles index: {str(e)}")

    # Fetch financial data once, share across all articles
    financial_context = None
    try:
        from scripts.fetch_financial_data import fetch_financial_data, format_financial_context
        fin_data = fetch_financial_data()
        financial_context = format_financial_context(fin_data)
        if financial_context:
            logger.info("Financial data loaded for prompt injection")
    except Exception as e:
        logger.warning(f"Financial data fetch failed (continuing without): {e}")

    articles = []
    used_topics = set()
    topic_index = 0

    while len(articles) < articles_count and topic_index < len(topics):
        topic_data = topics[topic_index]
        topic = topic_data.get('keyword', topic_data.get('title', 'Unknown Topic'))
        topic_index += 1

        # Skip if topic already used
        if topic.lower() in used_topics:
            logger.info(f"Skipping duplicate topic: {topic}")
            continue

        # Duplicate check (force topics skip this entirely)
        topic_lower = topic.lower()
        is_duplicate = False
        skip_dup = topic_data.get('_skip_duplicate', False)

        if skip_dup:
            logger.info(f"  Force topic — skipping duplicate check")
        else:
            for existing_kw in existing_keywords:
                if _is_similar(topic_lower, existing_kw, threshold=0.4):
                    logger.info(f"Skipping similar keyword (keyword match): '{topic}' ~ '{existing_kw}'")
                    is_duplicate = True
                    break
            if not is_duplicate:
                for existing_title in existing_titles:
                    if _is_similar(topic_lower, existing_title, threshold=0.35):
                        logger.info(f"Skipping similar topic (title match): '{topic}' ~ '{existing_title}'")
                        is_duplicate = True
                        break
            if not is_duplicate:
                for used in used_topics:
                    if _is_similar(topic_lower, used, threshold=0.4):
                        logger.info(f"Skipping similar topic in batch: '{topic}' ~ '{used}'")
                        is_duplicate = True
                        break

        if is_duplicate:
            continue

        quick_cat = topic_data.get('_quick_cat', '?')
        author_name = _get_author_for_category(quick_cat)
        source = topic_data.get('source', 'unknown')
        logger.info(f"{'=' * 70}")
        logger.info(f"  Article {len(articles)+1}/{articles_count}")
        logger.info(f"  Topic:    {topic}")
        logger.info(f"  Category: {quick_cat} | Author: {author_name} | Source: {source}")

        # Collect real search data for this topic (use Gemini-extracted keyword if available)
        search_context = None
        try:
            from scripts.fetch_search_queries import enrich_topic_with_search_data
            ai_keyword = topic_data.get('_ai_core_keyword', '')
            search_context = enrich_topic_with_search_data(
                topic, core_keyword_override=ai_keyword or None
            )
        except Exception as e:
            logger.warning(f"Search enrichment failed for '{topic}': {e}")

        # Skip topics with zero search demand (no one is searching for this)
        ac_count = len(search_context.get('autocomplete', [])) if search_context else 0
        if ac_count == 0:
            logger.info(f"Skipping topic with 0 autocomplete results (no search demand): {topic}")
            continue

        # Fetch real news articles for benchmarking (Naver + Google News)
        news_context = None
        try:
            from scripts.fetch_news_context import fetch_news_context
            ai_keyword = topic_data.get('_ai_core_keyword', '')
            news_context = fetch_news_context(ai_keyword or topic, max_articles=8)
        except Exception as e:
            logger.warning(f"News context fetch failed for '{topic}': {e}")

        source_url = topic_data.get('url', '')
        article = generate_article(
            topic,
            existing_articles=existing_articles_for_links,
            source_url=source_url,
            author_name=author_name,
            search_context=search_context,
            financial_context=financial_context,
            news_context=news_context,
            category=quick_cat,
            **kwargs,
        )

        if article and article.get('title'):
            wc = article.get('word_count', 0)

            # 1000어절 미만은 폐기 (AdSense 품질 기준 강화)
            if wc < 1000:
                logger.warning(f"  DISCARD ({wc} words < 1000 minimum): {article.get('title', '')[:50]}")
                logger.info(f"{'=' * 70}")
                continue

            # Post-generation semantic duplicate check
            if existing_titles and _is_semantic_duplicate(article['title'], existing_titles):
                logger.info(f"  SKIP (duplicate): '{article['title']}'")
                logger.info(f"{'=' * 70}")
                continue

            if wc < 1500:
                logger.warning(f"  Word count below target ({wc}/1500), publishing anyway")

            # Claude Haiku 팩트체크 + 수정
            logger.info(f"  Running Claude factcheck...")
            article = _factcheck_and_fix_with_claude(article)
            wc = article.get('word_count', wc)

            article['source_data'] = topic_data
            articles.append(article)
            used_topics.add(topic.lower())
            existing_titles.add(article['title'].lower())

            provider = article.get('_provider', 'unknown')
            source = topic_data.get('source', 'unknown')
            final_cat = article.get('topic', '?')
            cat_changed = f" (소스: {quick_cat} → 최종: {final_cat})" if final_cat != quick_cat else ""
            logger.info(f"  >> PUBLISHED")
            logger.info(f"     제목:     {article['title']}")
            logger.info(f"     최종카테고리: {final_cat}{cat_changed}")
            logger.info(f"     모델:     {provider} | 소스: {source}")
            logger.info(f"     단어수:   {wc} | 키워드: {article.get('keywords', [])}")
        else:
            logger.warning(f"  >> FAILED to generate article for: {topic}")
        logger.info(f"{'=' * 70}")

    logger.info(f"Successfully generated {len(articles)} unique articles")

    return articles


if __name__ == "__main__":
    print("Testing content generation...\n")

    test_topic = "Artificial Intelligence in Healthcare"

    print(f"Generating article about: {test_topic}")
    article = generate_article(
        topic=test_topic,
        min_words=500,
        max_words=800
    )

    if article:
        print("\n=== Generated Article ===")
        print(f"Provider: {article.get('_provider', 'unknown')}")
        print(f"Title: {article['title']}")
        print(f"Meta: {article['meta_description']}")
        print(f"Word Count: {article['word_count']}")
        print(f"Reading Time: {article['reading_time']} minutes")
        print(f"Keywords: {', '.join(article['keywords'][:5])}")
        print(f"\nContent Preview (first 200 chars):")
        print(article['content'][:200] + "...")
    else:
        print("Failed to generate article")
