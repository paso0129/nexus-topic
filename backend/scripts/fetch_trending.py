"""
Trending Topic Fetcher

Collects trending topics from two sources:
- Google Trends (US/UK/CA daily trends RSS)
- Reddit (category-balanced subreddits)
"""

import logging
import re
import time
from typing import List, Dict
from datetime import datetime

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reddit subreddits mapped to site categories for balanced topic collection
SUBREDDIT_MAP = {
    'TECH': ['technology', 'gadgets'],
    'IT & BIZ': ['artificial', 'startups'],
    'ECONOMY': ['economics', 'stocks', 'CryptoCurrency'],
    'ENTERTAINMENT': ['movies', 'television'],
    'GAMING': ['gaming', 'Games'],
    'HEALTH': ['Health', 'medicine'],
    'SCIENCE': ['science', 'space'],
    'POLICY': ['politics', 'worldnews'],
    'CULTURE': ['culture', 'books'],
}


def fetch_google_trends(
    markets: List[str] = ['US', 'UK', 'CA'],
    limit: int = 10
) -> List[Dict]:
    """
    Fetch trending searches from Google Trends daily trends RSS.

    Args:
        markets: List of country codes (e.g., ['US', 'UK', 'CA'])
        limit: Maximum number of trends per market

    Returns:
        List of trending topics with metadata
    """
    logger.info(f"Fetching Google Trends for markets: {markets}")
    trends_list = []

    DAILY_TRENDS_URL = "https://trends.google.com/trending/rss?geo={geo}"

    for market in markets:
        try:
            resp = requests.get(
                DAILY_TRENDS_URL.format(geo=market),
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=15,
            )
            resp.raise_for_status()

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


def fetch_reddit_hot(limit_per_sub: int = 10) -> List[Dict]:
    """
    Fetch hot posts from Reddit across category-balanced subreddits.

    Uses Reddit's public JSON API (no auth required).
    Respects rate limits with 2-second delay between requests.

    Args:
        limit_per_sub: Maximum posts to fetch per subreddit

    Returns:
        List of trending topics with metadata
    """
    logger.info("Fetching Reddit hot posts across all categories")
    trends_list = []
    headers = {'User-Agent': 'NexusTopic/1.0 (trending topic collector)'}

    for category, subreddits in SUBREDDIT_MAP.items():
        for subreddit in subreddits:
            try:
                resp = requests.get(
                    f'https://www.reddit.com/r/{subreddit}/hot.json?limit={limit_per_sub + 5}',
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                count = 0
                for post in data.get('data', {}).get('children', []):
                    post_data = post.get('data', {})

                    # Skip stickied/pinned posts
                    if post_data.get('stickied', False):
                        continue

                    title = post_data.get('title', '').strip()
                    if not title:
                        continue

                    trends_list.append({
                        'keyword': title,
                        'source': f'reddit_{subreddit.lower()}',
                        'score': post_data.get('ups', 0),
                        'region': 'global',
                        'url': f"https://www.reddit.com{post_data.get('permalink', '')}",
                        'timestamp': datetime.now().isoformat(),
                    })
                    count += 1

                    if count >= limit_per_sub:
                        break

                logger.info(f"Fetched {count} posts from r/{subreddit} ({category})")

            except Exception as e:
                logger.warning(f"Reddit r/{subreddit} fetch failed: {str(e)}")
                continue

            # Rate limit: 2 seconds between subreddit requests
            time.sleep(2)

    logger.info(f"Total Reddit posts fetched: {len(trends_list)}")
    return trends_list


def get_all_trending_topics(
    markets: List[str] = ['US', 'UK', 'CA'],
    limit_per_source: int = 15,
    **kwargs,
) -> List[Dict]:
    """
    Fetch trending topics from Google Trends + Reddit and combine them.

    Args:
        markets: Countries for Google Trends
        limit_per_source: Number of items per source
        **kwargs: Ignored (backward compatibility)

    Returns:
        Combined and sorted list of trending topics
    """
    logger.info("Fetching trending topics from Google Trends + Reddit")

    google_trends = fetch_google_trends(markets=markets, limit=limit_per_source)
    reddit_trends = fetch_reddit_hot(limit_per_sub=limit_per_source)

    # Normalize scores to 0-100 scale so different sources are comparable
    def _normalize(trends: list) -> list:
        if not trends:
            return trends
        scores = [t['score'] for t in trends]
        max_score = max(scores) or 1
        for t in trends:
            t['score'] = round((t['score'] / max_score) * 100)
        return trends

    _normalize(google_trends)
    _normalize(reddit_trends)

    all_trends = google_trends + reddit_trends

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

    # Filter out war/conflict/military topics (AdSense policy compliance)
    EXCLUDED_KEYWORDS = [
        'war ', ' war', 'warfare', 'invasion', 'invade',
        'bombing', 'airstrike', 'air strike', 'missile strike',
        'death toll', 'genocide', 'massacre', 'casualties',
        'military attack', 'military offensive', 'armed conflict',
        'troop', 'troops deploy', 'frontline', 'battlefield',
        'ceasefire', 'occupation', 'siege',
        'ukraine war', 'russia ukraine', 'gaza', 'hamas', 'hezbollah',
        'killed in', 'civilian deaths', 'war crimes',
        # Iran/US conflict
        'iran attack', 'iran strike', 'iran bomb', 'iran war',
        'iran missile', 'iran retaliation', 'iran conflict',
        'attacks on iran', 'strike on iran', 'iran nuclear strike',
        'iranian drone', 'iran us war', 'iran military',
        # General violence / sensitive events
        'terrorist', 'terrorism', 'hostage', 'execution',
        'assassination', 'coup', 'civil war', 'ethnic cleansing',
        'refugee crisis', 'displacement', 'sanctions on',
    ]
    before_filter = len(unique_trends)
    unique_trends = [
        t for t in unique_trends
        if not any(excl in f' {t["keyword"].lower()} ' for excl in EXCLUDED_KEYWORDS)
    ]
    excluded_count = before_filter - len(unique_trends)
    if excluded_count > 0:
        logger.info(f"Excluded {excluded_count} war/conflict-related topics")

    logger.info(f"Total trending topics collected: {len(unique_trends)} (from {len(all_trends)} raw)")
    logger.info(f"Sources: Google Trends={len(google_trends)}, Reddit={len(reddit_trends)}")

    return unique_trends


if __name__ == "__main__":
    print("Testing trending topic fetchers...\n")

    print("=== Google Trends ===")
    google_results = fetch_google_trends(markets=['US'], limit=5)
    for trend in google_results:
        print(f"  - {trend['keyword']} (Score: {trend['score']}, Region: {trend['region']})")

    print("\n=== Reddit Hot ===")
    reddit_results = fetch_reddit_hot(limit_per_sub=3)
    for trend in reddit_results[:15]:
        print(f"  - [{trend['source']}] {trend['keyword'][:60]}... (Score: {trend['score']})")

    print("\n=== All Combined ===")
    all_results = get_all_trending_topics(
        markets=['US'],
        limit_per_source=3
    )
    for trend in all_results[:15]:
        print(f"  - {trend['keyword'][:60]}... (Source: {trend['source']}, Score: {trend['score']})")
