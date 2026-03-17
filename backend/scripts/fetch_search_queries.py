"""
Fetch real search query data for SEO-optimized article generation.

Sources:
- Google Autocomplete API (suggestqueries.google.com)
- pytrends related_queries() (Google Trends)

All functions are fail-safe: errors return empty data, never block article generation.
"""

import json
import logging
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def fetch_autocomplete(keyword: str, delay: float = 1.0) -> list[str]:
    """Fetch Google Autocomplete suggestions for a keyword with multiple query variations.

    Queries 6 variations: base, "how {kw}", "why {kw}", "what {kw}", "is {kw}", "{kw} vs".
    Returns deduplicated list of suggestion strings.
    """
    prefixes = [
        "",
        "how ",
        "why ",
        "what ",
        "is ",
    ]
    suffixes = [" vs"]

    queries = [f"{p}{keyword}" for p in prefixes] + [f"{keyword}{s}" for s in suffixes]
    suggestions = []
    seen = set()

    for query in queries:
        try:
            encoded = urllib.parse.quote(query)
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={encoded}&hl=ko"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Response format: ["query", ["suggestion1", "suggestion2", ...]]
            if isinstance(data, list) and len(data) >= 2:
                for s in data[1]:
                    s_lower = s.lower().strip()
                    if s_lower not in seen and s_lower != keyword.lower().strip():
                        seen.add(s_lower)
                        suggestions.append(s)
            time.sleep(delay)
        except Exception as e:
            logger.debug(f"Autocomplete failed for '{query}': {e}")
            continue

    logger.info(f"Autocomplete: collected {len(suggestions)} suggestions for '{keyword}'")
    return suggestions


def fetch_related_queries(keyword: str, delay: float = 3.0) -> dict:
    """Fetch related queries from Google Trends via pytrends.

    Returns {'top': [...], 'rising': [...]}.
    Gracefully returns empty dict if pytrends is not installed or fails.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.debug("pytrends not installed, skipping related queries")
        return {"top": [], "rising": []}

    for attempt in range(2):
        try:
            if attempt > 0:
                time.sleep(delay * 2)
            time.sleep(delay)
            pytrends = TrendReq(hl="ko", tz=540)
            pytrends.build_payload([keyword], timeframe="now 7-d", geo="KR")
            related = pytrends.related_queries()

            result = {"top": [], "rising": []}
            kw_data = related.get(keyword, {})

            top_df = kw_data.get("top")
            if top_df is not None and not top_df.empty:
                result["top"] = top_df["query"].tolist()[:10]

            rising_df = kw_data.get("rising")
            if rising_df is not None and not rising_df.empty:
                result["rising"] = rising_df["query"].tolist()[:10]

            logger.info(
                f"Related queries: {len(result['top'])} top, {len(result['rising'])} rising for '{keyword}'"
            )
            return result
        except Exception as e:
            logger.debug(f"pytrends attempt {attempt + 1} failed for '{keyword}': {e}")
            continue

    logger.warning(f"pytrends failed after 2 attempts for '{keyword}'")
    return {"top": [], "rising": []}


def _extract_core_keyword_fallback(keyword: str) -> str:
    """Simple fallback: strip punctuation, skip common words, take first 2 significant words."""
    import re
    _skip = {
        'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or',
        'is', 'are', 'was', 'were', 'has', 'have', 'had', 'be', 'been',
        'how', 'why', 'what', 'when', 'where', 'who', 'which', 'that', 'this',
        'its', 'it', 'by', 'with', 'from', 'as', 'but', 'not', 'no', 'so',
        'your', 'you', 'our', 'we', 'they', 'their', 'my', 'will', 'would',
        'new', 'just', 'more', 'most', 'up', 'out', 'may', 'can', 'do', 'does',
        'star', 'reveals', 'says', 'tells', 'six', 'dear',
        # 한국어 불용어
        '이', '그', '저', '것', '수', '등', '및', '의', '를', '을', '에',
        '은', '는', '가', '이런', '그런', '또', '더', '위해', '대한',
    }
    words = keyword.split()
    core = []
    for w in words:
        cleaned = re.sub(r"[^a-zA-Z0-9]", '', w).strip()
        if cleaned.lower() not in _skip and len(cleaned) > 1:
            core.append(cleaned)
        if len(core) >= 2:
            break
    if not core:
        core = [re.sub(r"[^a-zA-Z0-9]", '', w) for w in words[:2] if len(w) > 1]
    return " ".join(core[:2])


def classify_and_extract_keywords(topics: list[dict]) -> list[dict]:
    """Use Gemini Flash to classify categories and extract search keywords for topics.

    Takes a list of topic dicts with 'keyword' field.
    Returns the same list with '_ai_category' and '_ai_core_keyword' added.
    Falls back to simple heuristics if Gemini fails.
    """
    import os
    import json as _json

    VALID_CATEGORIES = {
        '경제', 'IT·테크', '글로벌 경제', '부동산', '연예', '스포츠',
    }

    # Build batch prompt — process up to 30 topics per call
    batch_size = 30
    for batch_start in range(0, len(topics), batch_size):
        batch = topics[batch_start:batch_start + batch_size]

        topic_lines = []
        for i, t in enumerate(batch):
            topic_lines.append(f"{i+1}. {t.get('keyword', '')[:120]}")

        prompt = f"""각 토픽을 정확히 하나의 카테고리로 분류하고, 2단어 Google 검색 키워드를 추출하세요.

카테고리: {', '.join(sorted(VALID_CATEGORIES))}

카테고리 규칙:
- 경제: 주식, 코스피, 코스닥, 금리, 환율, 물가, 한국은행, 기업 실적
- IT·테크: AI, 반도체, 삼성, 애플, 소프트웨어, 스타트업, 클라우드
- 글로벌 경제: 나스닥, 연준, 달러, 유가, 비트코인, 관세, 무역전쟁
- 부동산: 아파트, 전세, 월세, 분양, 청약, 재건축, 대출
- 연예: 드라마, 영화, 아이돌, K-POP, 넷플릭스, 예능
- 스포츠: 축구, 야구, KBO, K리그, MLB, NBA, 올림픽

키워드 규칙:
- 실제 사용자가 Google에 입력할 2단어를 추출
- 핵심 명사 위주, 동사나 형용사 제외
- 예시: "삼성 반도체", "코스피 전망", "비트코인 시세"

토픽:
{chr(10).join(topic_lines)}

JSON 배열로만 응답, 마크다운 없이:
[{{"id":1,"category":"IT·테크","keyword":"삼성 반도체"}},{{"id":2,"category":"경제","keyword":"코스피 전망"}}]"""

        try:
            from google import genai
            from google.genai import types as genai_types

            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                raise RuntimeError("No API key")

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                ),
            )

            # Parse response
            text = response.text.strip()
            # Strip markdown code fences if present
            text = text.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            results = _json.loads(text)

            for item in results:
                idx = item.get('id', 0) - 1
                if 0 <= idx < len(batch):
                    cat = item.get('category', 'TECH').upper()
                    if cat not in VALID_CATEGORIES:
                        cat = 'IT·테크'
                    batch[idx]['_ai_category'] = cat
                    batch[idx]['_ai_core_keyword'] = item.get('keyword', '')[:50]

            classified = sum(1 for t in batch if '_ai_category' in t)
            logger.info(f"Gemini classified {classified}/{len(batch)} topics")

        except Exception as e:
            logger.warning(f"Gemini classification failed: {e}")

        # Fallback for any topics that weren't classified
        for t in batch:
            if '_ai_category' not in t:
                t['_ai_category'] = t.get('_quick_cat', 'IT·테크')
            if '_ai_core_keyword' not in t:
                t['_ai_core_keyword'] = _extract_core_keyword_fallback(t.get('keyword', ''))

    return topics


def enrich_topic_with_search_data(keyword: str, core_keyword_override: str = None) -> dict:
    """Collect autocomplete + related queries for a topic keyword.

    Args:
        keyword: Full topic title/keyword
        core_keyword_override: Pre-extracted core keyword from Gemini (skips local extraction)

    Returns {'autocomplete': [...], 'related_top': [...], 'related_rising': [...]}.
    """
    # Use Gemini-extracted keyword if available, otherwise fallback
    core_keyword = core_keyword_override or _extract_core_keyword_fallback(keyword)
    # Truncate original for pytrends (accepts longer queries)
    words = keyword.split()
    pytrends_keyword = " ".join(words[:5]) if len(words) > 5 else keyword

    result = {"autocomplete": [], "related_top": [], "related_rising": []}

    logger.info(f"Search enrichment: core='{core_keyword}', pytrends='{pytrends_keyword}'")

    try:
        result["autocomplete"] = fetch_autocomplete(core_keyword)
        # Fallback: if 2-word query got 0 results, try first word only
        if not result["autocomplete"] and " " in core_keyword:
            single = core_keyword.split()[0]
            logger.info(f"Autocomplete 0 results for '{core_keyword}', retrying with '{single}'")
            result["autocomplete"] = fetch_autocomplete(single)
    except Exception as e:
        logger.warning(f"Autocomplete collection failed for '{core_keyword}': {e}")

    try:
        related = fetch_related_queries(pytrends_keyword)
        result["related_top"] = related.get("top", [])
        result["related_rising"] = related.get("rising", [])
    except Exception as e:
        logger.warning(f"Related queries collection failed for '{pytrends_keyword}': {e}")

    total = len(result["autocomplete"]) + len(result["related_top"]) + len(result["related_rising"])
    logger.info(f"Search enrichment: {total} queries collected for '{core_keyword}'")
    return result
