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
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={encoded}"
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
            pytrends = TrendReq(hl="en-US", tz=360)
            pytrends.build_payload([keyword], timeframe="now 7-d")
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
        'IT & BIZ', 'CULTURE', 'ECONOMY', 'ENTERTAINMENT',
        'GAMING', 'HEALTH', 'POLICY', 'SCIENCE', 'TECH',
    }

    # Build batch prompt — process up to 30 topics per call
    batch_size = 30
    for batch_start in range(0, len(topics), batch_size):
        batch = topics[batch_start:batch_start + batch_size]

        topic_lines = []
        for i, t in enumerate(batch):
            topic_lines.append(f"{i+1}. {t.get('keyword', '')[:120]}")

        prompt = f"""Classify each topic into exactly ONE category and extract a 2-word Google search keyword.

Categories: {', '.join(sorted(VALID_CATEGORIES))}

Rules for category:
- ECONOMY: stocks, markets, finance, crypto, trade, tariffs, earnings, GDP, inflation
- ENTERTAINMENT: movies, TV, celebrities, music, actors, streaming
- TECH: hardware, gadgets, chips, phones, devices, EVs, batteries
- IT & BIZ: AI, startups, SaaS, cloud, software, enterprise, funding
- SCIENCE: research, space, NASA, physics, biology, discoveries
- HEALTH: medical, drugs, diseases, FDA, wellness, mental health
- POLICY: government, legislation, elections, regulation, courts
- GAMING: video games, consoles, esports, game studios
- CULTURE: art, social trends, lifestyle, books, fashion, food

Rules for keyword:
- Extract exactly 2 words that people would actually type into Google
- Use the main subject/noun, not verbs or adjectives
- Examples: "Bruce Campbell cancer" not "Evil Dead Star", "Apple MacBook" not "New Chips"

Topics:
{chr(10).join(topic_lines)}

Respond in JSON array format only, no markdown:
[{{"id":1,"category":"TECH","keyword":"Apple MacBook"}},{{"id":2,"category":"ECONOMY","keyword":"Bitcoin ETF"}}]"""

        try:
            from google import genai
            from google.genai import types as genai_types

            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                raise RuntimeError("No API key")

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
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
                        cat = 'TECH'
                    batch[idx]['_ai_category'] = cat
                    batch[idx]['_ai_core_keyword'] = item.get('keyword', '')[:50]

            classified = sum(1 for t in batch if '_ai_category' in t)
            logger.info(f"Gemini classified {classified}/{len(batch)} topics")

        except Exception as e:
            logger.warning(f"Gemini classification failed: {e}")

        # Fallback for any topics that weren't classified
        for t in batch:
            if '_ai_category' not in t:
                t['_ai_category'] = t.get('_quick_cat', 'TECH')
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
