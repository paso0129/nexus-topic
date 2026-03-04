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


def _extract_core_keyword(keyword: str) -> str:
    """Extract 2-3 core words from a long keyword for better API results.

    Strips filler words, title grammar words, and source names.
    Keeps the most meaningful nouns/topics for autocomplete.
    """
    filler = {
        # Time/recency
        'latest', 'news', 'today', 'trends', 'trending', 'update', 'updates',
        'current', 'recent', 'breaking', 'new', 'top', 'best', 'guide',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        '2024', '2025', '2026', '2027',
        # Title grammar / structure words
        'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'has', 'have', 'had',
        'how', 'why', 'what', 'when', 'where', 'who', 'which', 'that', 'this',
        'its', 'it', 'by', 'with', 'from', 'as', 'but', 'not', 'no', 'so',
        'if', 'about', 'into', 'than', 'just', 'also', 'more', 'most', 'some', 'only', 'every', 'many',
        'will', 'would', 'could', 'should', 'can', 'may', 'might',
        'do', 'does', 'did', 'your', 'you', 'our', 'we', 'they', 'their',
        'show', 'shows', 'explain', 'explains', 'chart', 'charts',
        'say', 'says', 'said', 'tell', 'tells', 'told', 'reveal', 'reveals',
        'report', 'reports', 'according', 'amid', 'after', 'before', 'during',
        'determine', 'determines', 'suggest', 'suggests', 'indicate', 'indicates',
        'announce', 'announces', 'aim', 'aims', 'raise', 'raises', 'hit', 'hits',
        'add', 'adds', 'set', 'sets', 'offer', 'offers', 'want', 'wants',
        'step', 'steps', 'need', 'needs', 'help', 'helps', 'support', 'supports',
        'community', 'tracker', 'watch',
        'still', 'gets', 'got', 'make', 'makes', 'made', 'take', 'takes',
        'go', 'goes', 'going', 'gone', 'come', 'comes', 'coming',
        'look', 'looks', 'looking', 'find', 'found', 'keep', 'keeps',
        'give', 'gives', 'back', 'over', 'out', 'up', 'down',
        'six', 'five', 'four', 'three', 'two', 'one', 'seven', 'eight', 'nine', 'ten',
        # Adjectives that dilute search (keep nouns)
        'extreme', 'massive', 'major', 'critical', 'shocking', 'brutal',
        'worst', 'weakening', 'growing', 'rising', 'falling', 'biggest',
        'selfish', 'viral', 'lethal', 'boring', 'great',
        # RSS title noise
        'exclusive', 'breaking', 'update', 'report', 'analysis',
        'star', 'reveals', 'cancel', 'cancels', 'upcoming',
        'deadline', 'appearances', 'convention', 'diagnosis',
        # Source names (often in RSS titles)
        'bloomberg', 'reuters', 'cnbc', 'techcrunch', 'wired',
        'lifehacker', 'arstechnica', 'theverge', 'bbc', 'cnn',
        'bloomberg.com', 'reuters.com', 'pennlivecom', 'triblivecom',
        'wfmzcom',
    }
    import re
    words = keyword.split()
    core = []
    for w in words:
        # Handle possessives FIRST: "YouTube's" → "YouTube", "China's" → "China"
        cleaned = re.sub(r"[\u2018\u2019\u0027]s\b", '', w)
        # Then strip ALL non-alphanumeric/space chars (catches every quote/punct variant)
        cleaned = re.sub(r"[^a-zA-Z0-9 ]", '', cleaned).strip()
        if cleaned.lower() not in filler and len(cleaned) > 1:
            core.append(cleaned)
    if not core:
        core = [re.sub(r"[.,!?:;\"'()\-–—]", '', w) for w in words[:2]]
    # Keep max 2 words — 2-word queries get far more autocomplete results than 3
    return " ".join(core[:2])


def enrich_topic_with_search_data(keyword: str) -> dict:
    """Collect autocomplete + related queries for a topic keyword.

    Extracts 2-3 core words for autocomplete, uses original for pytrends.
    Returns {'autocomplete': [...], 'related_top': [...], 'related_rising': [...]}.
    """
    # Extract core keyword for autocomplete (short = better results)
    core_keyword = _extract_core_keyword(keyword)
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
