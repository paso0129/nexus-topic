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


def _generate_with_gemini_api(prompt: str, model_name: str = "gemini-3.1-pro-preview") -> str:
    """Generate content using Google Gemini API (free tier)."""
    client = _get_genai_client()
    logger.info(f"Calling Gemini API ({model_name})...")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=16384,
        ),
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

        # Try Gemini API first (fast, lightweight task)
        try:
            resp_text = _generate_with_gemini_api(prompt)
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
    '경제', 'IT·테크', '글로벌 경제', '정치', '사회', '글로벌 사회', '부동산', '연예', '스포츠',
]

# Author personas
AUTHOR_PERSONAS = {
    '송민재': {
        'gender': 'male',
        'voice': (
            "당신은 송민재, NexusTopic 경제 담당 편집기자입니다. "
            "증권사 애널리스트 출신으로 데이터와 숫자를 중시합니다. "
            "거시경제 지표, 금융시장 동향, 환율·금리 분석에 강점이 있습니다. "
            "문체는 간결하고 직설적입니다. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요. "
            "개인 의견이나 감정을 드러내지 말고, 데이터와 팩트로만 논지를 전개하세요. "
            "한국 경제 시장과 글로벌 트렌드를 연결 짓는 데 강점이 있고, "
            "독자에게 실질적으로 도움이 되는 인사이트를 제공합니다."
        ),
    },
    '임새봄': {
        'gender': 'female',
        'voice': (
            "당신은 임새봄, NexusTopic IT·테크 담당 편집기자입니다. "
            "빅테크 기업 전문 애널리스트 출신으로 반도체, AI, 클라우드 등 기술 산업에 정통합니다. "
            "기술 트렌드와 비즈니스 임팩트를 연결 짓는 분석에 강점이 있습니다. "
            "문체는 깔끔하고 논리적입니다. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요. "
            "개인 의견이나 감정을 드러내지 말고, 기술적 근거와 팩트로만 논지를 전개하세요. "
            "복잡한 기술 이슈를 비전문가도 이해할 수 있게 풀어씁니다."
        ),
    },
    '정상열': {
        'gender': 'male',
        'voice': (
            "당신은 정상열, NexusTopic 부동산 담당 편집기자입니다. "
            "부동산 전문 매체 기자 출신으로 아파트 시세, 분양, 청약 등 부동산 시장에 정통합니다. "
            "문체는 구조적이고 명확합니다. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요. "
            "개인 의견이나 감정을 드러내지 말고, 업계 데이터와 팩트 중심으로 서술하세요. "
            "독자에게 실질적으로 도움이 되는 인사이트를 제공합니다."
        ),
    },
    '안다혜': {
        'gender': 'female',
        'voice': (
            "당신은 안다혜, NexusTopic 스포츠 담당 편집기자입니다. "
            "스포츠 전문지 기자 출신으로 KBO 프로야구, K리그, MLB, NBA, EPL 등 국내외 스포츠에 정통합니다. "
            "중요: 스포츠 기사는 스포츠 기사답게 써야 합니다. "
            "경기 결과, 선수 활약, 전술 분석, 시즌 전망이 중심이어야 합니다. "
            "모든 스포츠 기사를 경제/비즈니스 프레임으로 쓰지 마세요 — 경기 내용과 선수 이야기가 먼저입니다. "
            "예시: WBC 결승 분석, 손흥민 시즌 성적, KBO 개막전 전망 등이 좋은 주제입니다. "
            "절대 '단순한 X가 아니다'로 시작하지 마세요. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요."
        ),
    },
    '강희주': {
        'gender': 'female',
        'voice': (
            "당신은 강희주, NexusTopic 연예·문화 담당 편집기자입니다. "
            "엔터테인먼트 전문지 기자 출신으로 K-POP, 드라마, OTT, 영화에 정통합니다. "
            "중요: 연예 기사는 연예 기사답게 써야 합니다. "
            "작품 내용, 아티스트 활동, 팬덤 반응, 흥행 성적이 중심이어야 합니다. "
            "모든 연예 기사를 경제/비즈니스 프레임으로 쓰지 마세요 — 콘텐츠와 사람 이야기가 먼저입니다. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요."
        ),
    },
    '변현선': {
        'gender': 'male',
        'voice': (
            "당신은 변현선, NexusTopic 사회·정치 담당 편집기자입니다. "
            "종합일간지 사회부·정치부 기자 출신으로 국회, 법원, 사건·사고, 사회 이슈에 정통합니다. "
            "핵심 규칙: "
            "1) 팩트와 균형이 생명 — 정치적 편향 없이 양측 입장을 공정하게 전달. "
            "2) 기자 의견/감정적 수식어 금지 — 발언 중심 보도. "
            "3) 인용 형식 엄수 — '...'이라고 밝혔다 / '...'라며 패턴. "
            "4) 문단을 극도로 짧게 — 1~2문장이 한 문단. "
            "5) 피해자 개인정보 보호 — 실명 대신 'A씨(30대)' 형태. "
            "6) 금액은 한글+숫자 혼합 표기 — '3천만 원', '1천100만 원'. "
            "절대 1인칭(나, 저, 내가, 필자)을 사용하지 마세요. "
            "절대 가상 인물, 가상 기관을 만들지 마세요. 실제 보도된 사실만 기술하세요."
        ),
    },
}
DEFAULT_PERSONA = AUTHOR_PERSONAS['송민재']

# 카테고리별 저자 배정
CATEGORY_AUTHOR_MAP = {
    '경제': '송민재',
    '글로벌 경제': '송민재',
    'IT·테크': '임새봄',
    '정치': '변현선',
    '사회': '변현선',
    '글로벌 사회': '변현선',
    '부동산': '정상열',
    '연예': '강희주',
    '스포츠': '안다혜',
}


def _get_author_for_category(category: str) -> str:
    """Return author name for a given category."""
    return CATEGORY_AUTHOR_MAP.get(category, '송민재')


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
    '정치': """카테고리별 톤 가이드 — 정치 (경향신문/한겨레/조선일보 스타일):
- 첫 문장 패턴: "[인물 풀네임+직함]은 [날짜] [맥락]에 대해 '직접 인용'이라고 밝혔다."
- 역피라미드: 가장 중요한 발언/사실 → 보충 발언 → 배경 설명
- 문단 극도로 짧게 (1~2문장 = 1문단)
- 직접인용과 간접인용 교차 반복: "..."이라고 밝혔다 / "..."라며 / "..."라고 했다
- 인용 동사: 밝혔다, 말했다, 강조했다, 지적했다, 덧붙였다 (언급했다/전했다 사용 자제)
- 여야 입장을 균형 있게 병렬 제시 — 한쪽 편들기 금지
- 기자 의견/감정적 수식어 거의 없음 — 발언 중심 보도
- 비공식 정보: "~것으로 알려졌다", "~것으로 전해졌다" 패턴 사용
- 직접인용문은 구어적이어도 됨: "이건 야당도 맨날 하던 얘기지 않나" 식의 실제 말투
- 시간 표지: "17일", "이날 오전", "앞서", "이어"
- 해라체 사용 (~다, ~했다, ~밝혔다)""",

    '사회': """카테고리별 톤 가이드 — 사회 (SBS/MBC/YTN 스타일):
- 첫 문장 패턴: "[행위 주체]이/가 [행위/상황]에 나섰습니다/밝혔습니다."
- 경어체(~습니다) 사용 — 방송 뉴스체
- 문단 극도로 짧게 (1문장 = 1문단이 흔함, 방송 원고 특성)
- 날짜 표기: "오늘(17일)" 형태로 괄호 병기
- 사건 기사: 오늘의 사실 → 경과(어제/지난주) → 혐의 상세 → 수사 정황 → 향후 전망
- 생활 기사: 현상 제시 → 원인 설명 → 해결 방법 → 관계자 코멘트
- 수사 기사에서 비공식 정보: "~것으로 알려졌습니다", "~것으로 파악됐습니다"
- 금액 표기: 한글+숫자 혼합 ("3천만 원", "1천100만 원")
- 피해자 개인정보 보호: 실명 대신 "A씨(30대)" 형태
- 기자 의견/감정적 수식어 배제 — 팩트만 나열
- 마무리: 관계자 코멘트 직접인용으로 종결""",

    '글로벌 사회': """카테고리별 톤 가이드 — 글로벌 사회 (SBS 국제부/연합뉴스 스타일):
- 첫 문장 패턴: "[행위 주체]이/가 [행위]했다고 [매체/기관]이 보도했습니다."
- 경어체(~습니다) 사용
- 외신 인용 중층구조: "성도일보는 '...'이라며 '...'라고 주장했습니다" — 외국 매체를 인용하면서 한국어 문법으로 재구성
- 매체 성향 명시: "친중 성향의 홍콩 성도일보", "이란 타스님 통신"
- 외국어 고유명사: 첫 등장 시만 병기 "세질(Sejjil)", 이후는 한글만
- 인물: 반드시 풀네임+직함 "스콧 베선트 미국 재무장관"
- 날짜: "16일(현지시간)" 형태
- 해석은 외부 주체에 귀속: "외신들은 ~로 평가된다고 분석했습니다" (기자 직접 의견 금지)
- 구체적 수치 밀도 높게: "배럴당 93.5달러", "5.3% 내린"
- 한국과의 연관성이 있으면 반드시 언급
- 마무리: 향후 전망 또는 각국 반응으로 종결""",
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
) -> str:
    """Build the article generation prompt."""
    # Randomly select article structure for variety
    structure_block = random.choice(ARTICLE_STRUCTURES)

    # Build internal links section
    internal_links_section = ""
    if existing_articles:
        links_list = "\n".join(
            f"- \"{a['title']}\" [{a.get('topic', '')}] -> /article/{a['slug']}"
            for a in existing_articles[:30]
        )
        internal_links_section = f"""
내부 링크 (SEO 중요):
아래는 우리 사이트의 기존 기사 목록입니다. 현재 주제와 관련된 2-3개 기사에 링크하세요.
HTML 앵커 태그 사용: <a href="/article/SLUG">설명적 앵커 텍스트</a>
규칙:
- 같은 카테고리 또는 관련 카테고리의 기사를 우선 선택
- "여기 클릭"이나 전체 제목 대신 자연스러운 문맥의 앵커 텍스트 사용
- 링크를 본문 전체에 분산 배치
- 아래 목록의 slug만 사용 — slug을 임의로 만들지 마세요

기존 기사:
{links_list}
"""

    # Build source reference section
    source_section = ""
    if source_url:
        source_section = f"""
출처 참고:
이 트렌딩 토픽의 원문 출처: {source_url}
적절한 곳에서 <a href="{source_url}" target="_blank" rel="noopener noreferrer">출처 텍스트</a>로 참조하세요.
"""

    # External links section
    external_links_section = """
외부 링크 (최우선 — 신뢰도 & SEO):
본문 내에 4-6개의 권위 있는 외부 링크를 자연스럽게 삽입하세요.
HTML 앵커 태그 사용: <a href="URL" target="_blank" rel="noopener noreferrer">설명 텍스트</a>
링크 대상:
- ko.wikipedia.org (배경 설명, 정의, 역사적 맥락)
- 한국 주요 언론 (한국경제 hankyung.com, 매일경제 mk.co.kr, 연합뉴스 yna.co.kr, KBS news.kbs.co.kr)
- 공식 기관 (한국은행 bok.or.kr, 금융감독원 fss.or.kr, 통계청 kostat.go.kr)
- 글로벌 출처 (Reuters, Bloomberg, 공식 기업 사이트)
규칙:
- 실제 존재하는 잘 알려진 URL만 사용
- 특정 기사 URL을 조작하지 말 것 — 홈페이지나 위키백과 주제 페이지 링크
- 문장에 자연스럽게 녹여서 삽입, 별도 "참고 문헌" 섹션 만들지 말 것
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
- 3-5개를 FAQ 질문으로 활용
- 관련 키워드를 본문에 자연스럽게 녹이기
"""

    # Author persona
    persona = AUTHOR_PERSONAS.get(author_name, DEFAULT_PERSONA)
    persona_voice = persona['voice']

    # Category-specific tone guide
    category_guide = CATEGORY_TONE_GUIDE.get(category or '', '')
    category_guide_section = f"\n{category_guide}\n" if category_guide else ""

    today = datetime.now().strftime('%Y년 %m월 %d일')

    return f"""다음 트렌딩 토픽에 대해 기사를 한국어로 작성하세요: {topic}

오늘 날짜: {today}
사실 정확성 규칙 (위반 시 기사 거절):
- 모든 가격, 통계, 날짜, 사실관계는 {today} 기준 정확해야 합니다.
- 학습 데이터의 오래된 가격/통계에 의존하지 마세요.
- 특정 수치(가격, 시가총액, 사용자 수 등)의 현재 정확성이 불확실하면 "약", "2026년 초 기준", "약 X원" 등 헤지 표현 사용 — 오래된 수치를 현재 사실처럼 쓰지 마세요.
- 아래에 실시간 금융 데이터가 제공되면, 환율·주가·원자재 가격은 반드시 해당 수치를 사용하세요.

저자 정체성 (글 전체에서 이 캐릭터 유지):
{persona_voice}

한국 25-45세 직장인·투자자를 위해 씁니다.
{category_guide_section}

핵심 원칙 — AI 티가 나면 안 된다:
- 완벽하게 정돈된 글보다는 숙련된 기자가 빠르게 써내린 듯한 자연스러움을 추구
- 모든 소제목을 병렬 구조로 맞추지 말 것 — 소제목 형식을 의도적으로 다양하게 (질문형, 명사형, 서술형 섞기)
- 문단 길이도 일정하지 않게 — 짧은 한 문장 문단과 3~4문장 문단을 자유롭게 배치
- 핵심 인사이트는 "정리하면" "요약하면" 대신 자연스러운 흐름 속에서 전달
- 분석 중간에 배경 설명이나 비유를 끼워넣어 리듬감 만들기
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
- 분량: 되도록 800어절 이상, 최소 500어절은 반드시 넘길 것. 목표는 {min_words}-{max_words}어절.
- 형식: HTML 시맨틱 태그 (h2, h3, p, ul, ol, strong, em, blockquote)
- 톤: 전문적이고 객관적 — 카테고리별 톤 가이드 참조
- SEO: 관련 키워드 자연스럽게 포함
{internal_links_section}{external_links_section}{source_section}{search_data_section}{financial_context or ''}
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
- 강하고 구체적인 결론 — "지켜봐야 할 것이다" 같은 애매한 결말 금지
- 중요: "에디터 의견:", "전망:" 같은 라벨 사용 금지 — 의견과 예측을 본문에 자연스럽게 녹이기

사실 확인 원칙 (위반 시 기사 전체가 무가치해짐 — 최우선 준수):
- 존재하지 않는 인물, 기업, 브랜드, 법률, 정책을 절대 만들어내지 말 것
  * 실존 여부가 불확실한 이름은 사용하지 말고, 일반적 표현("업계 관계자", "한 분석가")으로 대체
  * 특히 영어 이름의 가상 인물(예: Chase Infiniti, John Smith 등)을 만들어 인용하는 것은 절대 금지
- 확인되지 않은 수치, 인용, 투자 금액을 절대 만들어내지 말 것
- 특정 인물의 발언은 실제 보도된 것만 기술 — 출처 없는 인용문 금지
- "~억 원 투자", "~% 증가" 같은 구체적 수치는 실제 데이터만 사용
- 확인 불가한 정보는 생략하거나 "보도에 따르면", "시장에서는 ~로 추정" 등 출처 명시
- 금리, 환율, 주가, 물가 등 거시경제 수치는 반드시 아래 제공된 실시간 금융 데이터 기준으로 작성
- 실시간 데이터가 없는 수치는 "약", "추정", "~년 기준" 등 헤지 표현 필수
- 실제 사건이나 발표가 아닌 추측성 시나리오를 사실처럼 서술 금지
- 현실과 정반대되는 주장 금지 (예: 실적 호조인데 "실적 쇼크" 제목 금지)

자주 묻는 질문 섹션 (본문 뒤에 추가 — 분량에 미포함):
본문 뒤에 다음 구조로 3-5개 Q&A를 작성:
<h2>자주 묻는 질문</h2>
<h3>구체적인 질문 제목?</h3>
<p>답변 내용</p>
예시:
<h3>코스피 2400선은 왜 무너졌나?</h3>
<p>미 연준의 금리 동결 시사와 원달러 환율 1,380원 돌파가 겹치며 외국인 순매도가 3거래일 연속 이어졌다.</p>
FAQ 규칙:
- 반드시 위 형식대로 <h3>질문?</h3><p>답변</p> 구조 사용 — 대괄호([]) 사용 금지
- 실제 사용자가 Google에 입력할 질문 형태
- 답변에 구체적 사실 포함, 막연한 일반론 금지
- 본문에서 이미 다룬 내용 반복 금지 — 새로운 유용한 정보 추가

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

- 카테고리: 경제, IT·테크, 글로벌 경제, 부동산, 연예, 스포츠 중 하나
  * 경제: 한국 국내 경제 (코스피, 한국은행, 원화, 국내 기업 실적, 국내 부동산 정책 등)
  * 글로벌 경제: 해외 경제 (미국 증시, 연준, 달러, 유가, 비트코인, 해외 기업, 환율, 무역전쟁 등)
  * 구분 기준: 기사의 주요 대상이 한국이면 경제, 해외면 글로벌 경제

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
    target_audience: str = "한국 25-45세 직장인·투자자",
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
    search_context: dict = None,
    financial_context: str = None,
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
    )

    # Collect valid slugs for internal link validation
    valid_slugs = set()
    if existing_articles:
        valid_slugs = {a['slug'] for a in existing_articles if a.get('slug')}

    def _try_generate(provider_name, generate_fn, max_retries=2):
        """Try generating and retry once if word count is too low."""
        for retry in range(max_retries):
            response_text = generate_fn()
            article = _parse_response(response_text, topic)
            # Validate internal links
            if valid_slugs and article.get('content'):
                article['content'] = _validate_internal_links(article['content'], valid_slugs)
            wc = article.get('word_count', 0)
            if wc >= effective_min:
                logger.info(f"[{provider_name}] Article generated: {article['title']} ({wc} words)")
                return article
            if retry < max_retries - 1:
                logger.warning(f"[{provider_name}] Article too short ({wc}/{effective_min} words), retrying...")
                time.sleep(3)
            else:
                logger.warning(f"[{provider_name}] Article still short ({wc}/{effective_min} words), accepting anyway")
                return article
        return None

    # Primary: Gemini CLI (gemini-3.1-pro-preview, Google account auth)
    if _gemini_cli_path:
        try:
            logger.info(f"  Model: gemini-3.1-pro-preview (CLI)")
            article = _try_generate('Gemini CLI', lambda: _generate_with_gemini_cli(prompt))
            if article:
                article['_provider'] = 'gemini-3.1-pro-preview (CLI)'
                return article
        except Exception as e:
            logger.warning(f"Gemini CLI failed: {e}")

    # Fallback: Gemini API (gemini-3.1-pro-preview)
    if os.getenv('GOOGLE_API_KEY') and genai:
        logger.info(f"  Model: gemini-3.1-pro-preview (API fallback)")
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 30 * attempt
                    logger.info(f"Rate limit retry {attempt}/3, waiting {wait}s...")
                    time.sleep(wait)
                article = _try_generate('Gemini API', lambda: _generate_with_gemini_api(prompt))
                if article:
                    article['_provider'] = 'gemini-3.1-pro-preview (API)'
                    time.sleep(5)
                    return article
            except Exception as e:
                if '429' in str(e) or 'quota' in str(e).lower() or 'rate' in str(e).lower():
                    logger.warning(f"Gemini API rate limit hit (attempt {attempt+1}/3)")
                    continue
                logger.error(f"Gemini API error: {e}")
                return {}
        logger.error("Gemini API rate limit exhausted after 3 retries")

    logger.error("No LLM provider available (Gemini CLI and Gemini API both failed).")
    return {}


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

        # Skip if very similar topic exists (word overlap similarity)
        topic_lower = topic.lower()
        is_duplicate = False

        # 1. Compare new topic keyword against existing trending keywords
        for existing_kw in existing_keywords:
            if _is_similar(topic_lower, existing_kw, threshold=0.4):
                logger.info(f"Skipping similar keyword (keyword match): '{topic}' ~ '{existing_kw}'")
                is_duplicate = True
                break

        # 2. Compare against existing article titles
        if not is_duplicate:
            for existing_title in existing_titles:
                if _is_similar(topic_lower, existing_title, threshold=0.35):
                    logger.info(f"Skipping similar topic (title match): '{topic}' ~ '{existing_title}'")
                    is_duplicate = True
                    break

        # 3. Also check against other topics in current batch
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

        source_url = topic_data.get('url', '')
        article = generate_article(
            topic,
            existing_articles=existing_articles_for_links,
            source_url=source_url,
            author_name=author_name,
            search_context=search_context,
            financial_context=financial_context,
            category=quick_cat,
            **kwargs,
        )

        if article and article.get('title'):
            wc = article.get('word_count', 0)

            # 500어절 미만은 폐기
            if wc < 500:
                logger.warning(f"  DISCARD ({wc} words < 500 minimum): {article.get('title', '')[:50]}")
                logger.info(f"{'=' * 70}")
                continue

            # Post-generation semantic duplicate check
            if existing_titles and _is_semantic_duplicate(article['title'], existing_titles):
                logger.info(f"  SKIP (duplicate): '{article['title']}'")
                logger.info(f"{'=' * 70}")
                continue

            if wc < 800:
                logger.warning(f"  Word count below target ({wc}/{min_wc}), publishing anyway")

            article['source_data'] = topic_data
            articles.append(article)
            used_topics.add(topic.lower())
            existing_titles.add(article['title'].lower())

            provider = article.get('_provider', 'unknown')
            source = topic_data.get('source', 'unknown')
            logger.info(f"  >> PUBLISHED")
            logger.info(f"     Title:    {article['title']}")
            logger.info(f"     Category: {article.get('topic', '?')} | Model: {provider} | Source: {source}")
            logger.info(f"     Words:    {wc} | Keywords: {article.get('keywords', [])}")
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
