"""
Trending Topic Fetcher

Collects trending topics from multiple sources:
- Google Trends
- HackerNews
"""

import logging
import re
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

    # Combine all sources
    all_trends.extend(hn_trends)
    all_trends.extend(google_trends)

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
    logger.info(f"Sources: HackerNews={len(hn_trends)}, Google={len(google_trends)}")

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
