"""
News Context Fetcher for Article Generation

Fetches real news articles about a topic from multiple sources
to provide factual context for AI article generation.

Sources:
1. Naver News Search API (Korean news — best coverage)
2. Google News RSS (global + Korean, no API key needed)
3. Korean media RSS feeds (SBS, 한경, 매경 — already in fetch_korean_news.py)

The fetched articles are summarized and injected into the generation prompt
so that Gemini writes based on real, current reporting — not stale training data.
"""

import logging
import os
import re
import xml.etree.ElementTree as ET
from html import unescape
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; NexusTopic/1.0)',
}

TIMEOUT = 10


# ---------------------------------------------------------------------------
# 1. Naver News Search API
# ---------------------------------------------------------------------------

def _fetch_naver_news(query: str, display: int = 5) -> List[Dict]:
    """
    Search Naver News API for recent articles about a topic.

    Requires NAVER_CLIENT_ID and NAVER_CLIENT_SECRET env vars.
    Free tier: 25,000 requests/day.
    https://developers.naver.com/docs/serviceapi/search/news/news.md
    """
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        return []

    url = 'https://openapi.naver.com/v1/search/news.json'
    params = {
        'query': query,
        'display': display,
        'sort': 'date',  # Most recent first
    }
    headers = {
        'X-Naver-Client-Id': client_id,
        'X-Naver-Client-Secret': client_secret,
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        articles = []
        for item in data.get('items', []):
            title = _clean_html(item.get('title', ''))
            description = _clean_html(item.get('description', ''))
            if not title:
                continue
            articles.append({
                'title': title,
                'description': description,
                'source': 'naver_news',
                'url': item.get('originallink') or item.get('link', ''),
                'pub_date': item.get('pubDate', ''),
            })
        logger.info(f"  Naver News: {len(articles)} articles for '{query}'")
        return articles

    except Exception as e:
        logger.warning(f"  Naver News API failed: {e}")
        return []


# ---------------------------------------------------------------------------
# 2. Google News RSS (no API key needed)
# ---------------------------------------------------------------------------

def _fetch_google_news_rss(query: str, limit: int = 5, lang: str = 'ko') -> List[Dict]:
    """
    Fetch Google News RSS for a search query.
    No API key required — uses public RSS endpoint.
    """
    encoded_query = quote_plus(query)
    # Google News RSS with Korean language and region
    url = f'https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl=KR&ceid=KR:{lang}'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        articles = []

        for item in root.findall('.//item')[:limit]:
            title_el = item.find('title')
            link_el = item.find('link')
            desc_el = item.find('description')
            pub_date_el = item.find('pubDate')
            source_el = item.find('source')

            title = title_el.text.strip() if title_el is not None and title_el.text else ''
            if not title:
                continue

            # Google News title format: "Article Title - Source Name"
            # Extract source from title suffix
            source_name = ''
            if source_el is not None and source_el.text:
                source_name = source_el.text.strip()
            elif ' - ' in title:
                title, source_name = title.rsplit(' - ', 1)

            desc = ''
            if desc_el is not None and desc_el.text:
                desc = _clean_html(desc_el.text)[:300]

            articles.append({
                'title': title.strip(),
                'description': desc,
                'source': f'google_news ({source_name})' if source_name else 'google_news',
                'url': link_el.text.strip() if link_el is not None and link_el.text else '',
                'pub_date': pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else '',
            })

        logger.info(f"  Google News RSS: {len(articles)} articles for '{query}'")
        return articles

    except Exception as e:
        logger.warning(f"  Google News RSS failed: {e}")
        return []


# ---------------------------------------------------------------------------
# 3. Utility
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    return text.strip()


def _deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """Remove duplicate articles by title similarity."""
    seen_titles = set()
    unique = []
    for a in articles:
        title_lower = a['title'].lower()
        # Skip if very similar title already seen
        is_dup = False
        for seen in seen_titles:
            if seen in title_lower or title_lower in seen:
                is_dup = True
                break
            # Simple word overlap check
            words_a = set(title_lower.split())
            words_b = set(seen.split())
            if words_a and words_b:
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
                if overlap > 0.7:
                    is_dup = True
                    break
        if not is_dup:
            seen_titles.add(title_lower)
            unique.append(a)
    return unique


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_news_context(
    topic: str,
    max_articles: int = 8,
    include_english: bool = True,
) -> Optional[str]:
    """
    Fetch real news articles about a topic from multiple sources.

    Returns a formatted string of article summaries to inject into
    the generation prompt, or None if no articles found.
    """
    logger.info(f"Fetching news context for: '{topic}'")
    all_articles: List[Dict] = []

    # 1. Naver News (Korean, best coverage)
    naver_results = _fetch_naver_news(topic, display=5)
    all_articles.extend(naver_results)

    # 2. Google News RSS (Korean)
    google_ko = _fetch_google_news_rss(topic, limit=5, lang='ko')
    all_articles.extend(google_ko)

    # 3. Google News RSS (English) — for global topics
    if include_english:
        google_en = _fetch_google_news_rss(topic, limit=3, lang='en')
        all_articles.extend(google_en)

    if not all_articles:
        logger.warning(f"  No news context found for '{topic}'")
        return None

    # Deduplicate and limit
    unique = _deduplicate_articles(all_articles)[:max_articles]
    logger.info(f"  News context: {len(unique)} unique articles (from {len(all_articles)} total)")

    # Format for prompt injection
    lines = [
        f"실제 뉴스 기사 참조 데이터 (이 기사들의 팩트와 수치를 참고하여 작성하세요):",
        f"아래는 '{topic}' 관련 최신 뉴스 기사 {len(unique)}건입니다.",
        f"이 기사들에서 보도된 팩트, 수치, 인용문을 참고하여 기사를 작성하세요.",
        f"아래 기사에 없는 내용을 지어내지 마세요.",
        "",
    ]
    for idx, a in enumerate(unique, 1):
        source = a['source']
        title = a['title']
        desc = a.get('description', '')
        url = a.get('url', '')
        pub_date = a.get('pub_date', '')

        lines.append(f"[참조기사 {idx}] ({source})")
        lines.append(f"  제목: {title}")
        if desc:
            lines.append(f"  요약: {desc}")
        if url:
            lines.append(f"  URL: {url}")
        if pub_date:
            lines.append(f"  날짜: {pub_date}")
        lines.append("")

    return "\n".join(lines)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else '코스피 증시 전망'
    context = fetch_news_context(query)
    if context:
        print(context)
    else:
        print("No news context found.")
