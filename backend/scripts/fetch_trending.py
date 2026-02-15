"""
Trending Topic Fetcher

Collects trending topics from multiple sources:
- Google Trends
- HackerNews
- Dev.to
- Product Hunt
- TechCrunch (RSS)
- The Verge (RSS)
- NewsAPI
"""

import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import List, Dict
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_google_trends(
    markets: List[str] = ['US', 'UK', 'CA', 'DE', 'FR'],
    limit: int = 10
) -> List[Dict]:
    """
    Fetch trending searches from Google Trends using the daily trends RSS/JSON API.
    Does not depend on pytrends to avoid urllib3 compatibility issues.

    Args:
        markets: List of country codes (e.g., ['US', 'UK', 'CA'])
        limit: Maximum number of trends per market

    Returns:
        List of trending topics with metadata
    """
    logger.info(f"Fetching Google Trends for markets: {markets}")
    trends_list = []

    # Google Trends daily trends API (no auth needed)
    DAILY_TRENDS_URL = "https://trends.google.com/trending/rss?geo={geo}"

    for market in markets:
        try:
            resp = requests.get(
                DAILY_TRENDS_URL.format(geo=market),
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()

            # Parse RSS XML for titles
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            items = root.findall('.//item/title')

            count = 0
            for idx, item in enumerate(items[:limit]):
                keyword = item.text
                if keyword and len(keyword.split()) >= 3:
                    trends_list.append({
                        'keyword': keyword,
                        'source': 'google_trends',
                        'score': limit - idx,
                        'region': market,
                        'timestamp': datetime.now().isoformat(),
                    })
                    count += 1

            logger.info(f"Fetched {count} trends from Google Trends ({market})")

        except Exception as e:
            logger.warning(f"Google Trends failed for {market}: {str(e)}")
            continue

    logger.info(f"Total trends fetched from Google: {len(trends_list)}")
    return trends_list


def fetch_hackernews_top(limit: int = 10) -> List[Dict]:
    """
    Fetch top stories from HackerNews.

    Args:
        limit: Number of stories to fetch

    Returns:
        List of trending topics with metadata
    """
    logger.info(f"Fetching top {limit} HackerNews stories")
    trends_list = []

    try:
        # Get top story IDs
        response = requests.get(
            'https://hacker-news.firebaseio.com/v0/topstories.json',
            timeout=10
        )
        response.raise_for_status()
        story_ids = response.json()[:limit]

        # Fetch story details
        for idx, story_id in enumerate(story_ids):
            try:
                story_response = requests.get(
                    f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json',
                    timeout=10
                )
                story_response.raise_for_status()
                story = story_response.json()

                if story and 'title' in story:
                    trends_list.append({
                        'keyword': story['title'],
                        'source': 'hackernews',
                        'score': story.get('score', 0),
                        'region': 'global',
                        'url': story.get('url', f'https://news.ycombinator.com/item?id={story_id}'),
                        'timestamp': datetime.now().isoformat()
                    })

            except Exception as e:
                logger.error(f"Error fetching HN story {story_id}: {str(e)}")
                continue

        logger.info(f"Fetched {len(trends_list)} stories from HackerNews")

    except Exception as e:
        logger.error(f"Error fetching HackerNews top stories: {str(e)}")

    return trends_list


def fetch_devto_trending(limit: int = 10) -> List[Dict]:
    """Fetch trending articles from Dev.to."""
    logger.info(f"Fetching top {limit} Dev.to articles")
    trends_list = []

    try:
        response = requests.get(
            'https://dev.to/api/articles',
            params={'top': 1, 'per_page': limit},
            headers={'User-Agent': 'NexusTopic/1.0'},
            timeout=10,
        )
        response.raise_for_status()
        articles = response.json()

        for article in articles:
            trends_list.append({
                'keyword': article['title'],
                'source': 'devto',
                'score': article.get('public_reactions_count', 0),
                'region': 'global',
                'url': article.get('url', ''),
                'timestamp': datetime.now().isoformat(),
            })

        logger.info(f"Fetched {len(trends_list)} articles from Dev.to")

    except Exception as e:
        logger.warning(f"Dev.to fetch failed: {str(e)}")

    return trends_list


def fetch_producthunt(limit: int = 10) -> List[Dict]:
    """Fetch today's top products from Product Hunt via Atom feed."""
    logger.info(f"Fetching top {limit} Product Hunt items")
    trends_list = []
    atom_ns = '{http://www.w3.org/2005/Atom}'

    try:
        response = requests.get(
            'https://www.producthunt.com/feed',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15,
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        entries = root.findall(f'{atom_ns}entry')

        for idx, entry in enumerate(entries[:limit]):
            title = entry.find(f'{atom_ns}title')
            link = entry.find(f'{atom_ns}link')
            if title is not None and title.text:
                link_url = link.get('href', '') if link is not None else ''
                trends_list.append({
                    'keyword': title.text,
                    'source': 'producthunt',
                    'score': limit - idx,
                    'region': 'global',
                    'url': link_url,
                    'timestamp': datetime.now().isoformat(),
                })

        logger.info(f"Fetched {len(trends_list)} items from Product Hunt")

    except Exception as e:
        logger.warning(f"Product Hunt fetch failed: {str(e)}")

    return trends_list


def fetch_tech_rss(limit: int = 10) -> List[Dict]:
    """Fetch latest articles from TechCrunch and The Verge via RSS."""
    logger.info("Fetching TechCrunch + The Verge RSS")
    trends_list = []

    feeds = [
        ('https://techcrunch.com/feed/', 'techcrunch'),
        ('https://www.theverge.com/rss/index.xml', 'theverge'),
    ]

    for feed_url, source_name in feeds:
        try:
            response = requests.get(
                feed_url,
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            response.raise_for_status()

            root = ET.fromstring(response.text)
            # Handle both RSS <item> and Atom <entry>
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('.//item')

            count = 0
            for idx, item in enumerate(items[:limit]):
                # Try Atom <title> then RSS <title>
                title = item.find('{http://www.w3.org/2005/Atom}title')
                if title is None:
                    title = item.find('title')
                link = item.find('{http://www.w3.org/2005/Atom}link')
                if link is None:
                    link = item.find('link')

                if title is not None and title.text:
                    link_url = ''
                    if link is not None:
                        link_url = link.get('href', '') or link.text or ''

                    trends_list.append({
                        'keyword': title.text.strip(),
                        'source': source_name,
                        'score': limit - idx,
                        'region': 'global',
                        'url': link_url,
                        'timestamp': datetime.now().isoformat(),
                    })
                    count += 1

            logger.info(f"Fetched {count} articles from {source_name}")

        except Exception as e:
            logger.warning(f"{source_name} RSS fetch failed: {str(e)}")
            continue

    return trends_list


def fetch_newsapi(limit: int = 10) -> List[Dict]:
    """Fetch top tech headlines from NewsAPI."""
    api_key = os.environ.get('NEWSAPI_KEY')
    if not api_key:
        logger.info("NEWSAPI_KEY not set, skipping NewsAPI")
        return []

    logger.info(f"Fetching top {limit} NewsAPI headlines")
    trends_list = []

    try:
        response = requests.get(
            'https://newsapi.org/v2/top-headlines',
            params={
                'category': 'technology',
                'language': 'en',
                'pageSize': limit,
                'apiKey': api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        for idx, article in enumerate(data.get('articles', [])):
            title = article.get('title', '')
            if title and title != '[Removed]':
                trends_list.append({
                    'keyword': title,
                    'source': 'newsapi',
                    'score': limit - idx,
                    'region': 'global',
                    'url': article.get('url', ''),
                    'timestamp': datetime.now().isoformat(),
                })

        logger.info(f"Fetched {len(trends_list)} headlines from NewsAPI")

    except Exception as e:
        logger.warning(f"NewsAPI fetch failed: {str(e)}")

    return trends_list


def get_all_trending_topics(
    markets: List[str] = ['US', 'UK', 'CA'],
    subreddits: List[str] = None,
    limit_per_source: int = 15
) -> List[Dict]:
    """
    Fetch trending topics from all sources and combine them.

    Args:
        markets: Countries for Google Trends
        subreddits: Unused (kept for backward compatibility)
        limit_per_source: Number of items per source

    Returns:
        Combined and sorted list of trending topics
    """
    logger.info("Fetching trending topics from all sources")

    all_trends = []

    hn_trends = fetch_hackernews_top(limit=limit_per_source)
    google_trends = fetch_google_trends(markets=markets, limit=limit_per_source)
    devto_trends = fetch_devto_trending(limit=limit_per_source)
    ph_trends = fetch_producthunt(limit=limit_per_source)
    rss_trends = fetch_tech_rss(limit=limit_per_source)
    newsapi_trends = fetch_newsapi(limit=limit_per_source)

    # Normalize scores to 0-100 scale so different sources are comparable
    def _normalize(trends: list) -> list:
        if not trends:
            return trends
        scores = [t['score'] for t in trends]
        max_score = max(scores) or 1
        for t in trends:
            t['score'] = round((t['score'] / max_score) * 100)
        return trends

    _normalize(hn_trends)
    _normalize(google_trends)
    _normalize(devto_trends)
    _normalize(ph_trends)
    _normalize(rss_trends)
    _normalize(newsapi_trends)

    # Combine all sources
    all_trends.extend(hn_trends)
    all_trends.extend(google_trends)
    all_trends.extend(devto_trends)
    all_trends.extend(ph_trends)
    all_trends.extend(rss_trends)
    all_trends.extend(newsapi_trends)

    # Boost high-CPC category keywords (finance, insurance, legal, health, AI/SaaS, real estate)
    HIGH_CPC_KEYWORDS = [
        # Finance & Insurance
        'insurance', 'mortgage', 'credit', 'loan', 'banking', 'invest', 'stock', 'crypto',
        'bitcoin', 'ethereum', 'finance', 'tax', 'trading', 'hedge fund', 'interest rate',
        'federal reserve', 'inflation', 'recession', 'economy', 'GDP', 'earnings',
        # Legal
        'lawsuit', 'regulation', 'compliance', 'patent', 'antitrust', 'court', 'legal',
        'privacy', 'GDPR', 'settlement',
        # Health & Pharma
        'health', 'medical', 'pharma', 'drug', 'FDA', 'clinical trial', 'vaccine',
        'healthcare', 'biotech', 'cancer', 'disease', 'therapy',
        # AI & SaaS & Tech Enterprise
        'artificial intelligence', ' AI ', 'machine learning', 'SaaS', 'cloud', 'enterprise',
        'cybersecurity', 'data breach', 'ransomware', 'startup', 'valuation', 'IPO',
        'acquisition', 'merger', 'funding', 'venture capital',
        # Real Estate
        'real estate', 'housing', 'property', 'rent', 'construction',
        # Energy
        'oil', 'energy', 'solar', 'EV ', 'electric vehicle', 'battery', 'nuclear',
    ]

    for trend in all_trends:
        keyword_lower = trend['keyword'].lower()
        cpc_matches = sum(1 for kw in HIGH_CPC_KEYWORDS if kw.lower().strip() in keyword_lower)
        if cpc_matches > 0:
            # Boost score by 50% per matching CPC keyword, cap at 3x
            multiplier = min(1.0 + (0.5 * cpc_matches), 3.0)
            trend['score'] = max(round(trend['score'] * multiplier), 50)
            trend['cpc_boost'] = True

    # Sort by boosted score (descending)
    all_trends.sort(key=lambda x: x['score'], reverse=True)

    # Remove duplicates (keep highest score) - word overlap similarity check
    unique_trends = []
    for trend in all_trends:
        keyword_lower = trend['keyword'].lower()
        is_dup = False
        for existing in unique_trends:
            existing_lower = existing['keyword'].lower()
            # Exact match
            if keyword_lower == existing_lower:
                is_dup = True
                break
            # Substring match
            if keyword_lower in existing_lower or existing_lower in keyword_lower:
                is_dup = True
                break
            # Word overlap: extract significant words (>2 chars) and check Jaccard similarity
            words_a = {w for w in re.findall(r'[a-z0-9]+', keyword_lower) if len(w) > 2}
            words_b = {w for w in re.findall(r'[a-z0-9]+', existing_lower) if len(w) > 2}
            if words_a and words_b:
                overlap = len(words_a & words_b) / len(words_a | words_b)
                if overlap >= 0.5:
                    is_dup = True
                    break
        if not is_dup:
            unique_trends.append(trend)

    logger.info(f"Total trending topics collected: {len(unique_trends)} (from {len(all_trends)} raw)")
    logger.info(f"Sources: HackerNews={len(hn_trends)}, Google={len(google_trends)}, "
                f"Dev.to={len(devto_trends)}, ProductHunt={len(ph_trends)}, "
                f"RSS={len(rss_trends)}, NewsAPI={len(newsapi_trends)}")

    return unique_trends


if __name__ == "__main__":
    # Test the functions
    print("Testing trending topic fetchers...\n")

    print("=== Google Trends ===")
    google_results = fetch_google_trends(markets=['US'], limit=5)
    for trend in google_results:
        print(f"  - {trend['keyword']} (Score: {trend['score']}, Region: {trend['region']})")

    print("\n=== HackerNews Top ===")
    hn_results = fetch_hackernews_top(limit=5)
    for trend in hn_results:
        print(f"  - {trend['keyword'][:60]}... (Score: {trend['score']})")

    print("\n=== All Combined ===")
    all_results = get_all_trending_topics(
        markets=['US'],
        limit_per_source=3
    )
    for trend in all_results[:10]:
        print(f"  - {trend['keyword'][:60]}... (Source: {trend['source']}, Score: {trend['score']})")
