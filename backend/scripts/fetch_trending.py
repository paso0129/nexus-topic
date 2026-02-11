"""
Trending Topic Fetcher

Collects trending topics from multiple sources:
- Google Trends
- Reddit
- HackerNews
"""

import logging
import re
from typing import List, Dict, Optional
from datetime import datetime
import os

try:
    from pytrends.request import TrendReq
except ImportError:
    TrendReq = None

try:
    import praw
except ImportError:
    praw = None

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
    Fetch trending searches from Google Trends (using daily trends).

    Args:
        markets: List of country codes (e.g., ['US', 'UK', 'CA'])
        limit: Maximum number of trends per market

    Returns:
        List of trending topics with metadata
    """
    if TrendReq is None:
        logger.error("pytrends is not installed. Install with: pip install pytrends")
        return []

    logger.info(f"Fetching Google Trends for markets: {markets}")
    trends_list = []

    try:
        pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 25), retries=2, backoff_factor=0.1)

        for market in markets:
            try:
                # Use realtime trending searches (more reliable)
                try:
                    trending_data = pytrends.realtime_trending_searches(pn=market)

                    if not trending_data.empty:
                        for idx, row in trending_data.head(limit).iterrows():
                            keyword = row.get('title', '') or row.get('entityNames', [''])[0]
                            if keyword:
                                trends_list.append({
                                    'keyword': keyword,
                                    'source': 'google_trends',
                                    'score': limit - len(trends_list),
                                    'region': market,
                                    'timestamp': datetime.now().isoformat(),
                                    'url': row.get('newsUrl', '')
                                })
                        logger.info(f"Fetched {len(trending_data)} realtime trends from {market}")
                        continue
                except Exception as e:
                    logger.warning(f"Realtime trends failed for {market}: {str(e)}, trying daily trends...")

                # Fallback to daily search trends
                try:
                    daily_trends = pytrends.today_searches(pn=market)
                    if not daily_trends.empty:
                        for idx, keyword in enumerate(daily_trends[0][:limit]):
                            trends_list.append({
                                'keyword': keyword,
                                'source': 'google_trends',
                                'score': limit - idx,
                                'region': market,
                                'timestamp': datetime.now().isoformat()
                            })
                        logger.info(f"Fetched {len(daily_trends)} daily trends from {market}")
                except Exception as e:
                    logger.warning(f"Daily trends also failed for {market}: {str(e)}")

            except Exception as e:
                logger.error(f"Error fetching trends for {market}: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error initializing Google Trends: {str(e)}")

    logger.info(f"Total trends fetched from Google: {len(trends_list)}")
    return trends_list


def fetch_reddit_trending(
    subreddits: List[str] = ['technology', 'worldnews'],
    limit: int = 10
) -> List[Dict]:
    """
    Fetch trending posts from Reddit.

    Args:
        subreddits: List of subreddit names
        limit: Number of posts to fetch per subreddit

    Returns:
        List of trending topics with metadata
    """
    if praw is None:
        logger.error("praw is not installed. Install with: pip install praw")
        return []

    client_id = os.getenv('REDDIT_CLIENT_ID')
    client_secret = os.getenv('REDDIT_CLIENT_SECRET')

    if not client_id or not client_secret:
        logger.warning("Reddit credentials not found in environment variables")
        return []

    logger.info(f"Fetching Reddit trends from: {subreddits}")
    trends_list = []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent='WordPress AdSense Automation Bot 1.0'
        )

        for subreddit_name in subreddits:
            try:
                subreddit = reddit.subreddit(subreddit_name)

                for idx, post in enumerate(subreddit.hot(limit=limit)):
                    trends_list.append({
                        'keyword': post.title,
                        'source': f'reddit_{subreddit_name}',
                        'score': post.score,
                        'region': 'global',
                        'url': f'https://reddit.com{post.permalink}',
                        'timestamp': datetime.now().isoformat()
                    })

                logger.info(f"Fetched {limit} posts from r/{subreddit_name}")

            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error initializing Reddit client: {str(e)}")

    logger.info(f"Total trends fetched from Reddit: {len(trends_list)}")
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
    subreddits: List[str] = ['technology', 'worldnews', 'business', 'science', 'news', 'artificial'],
    limit_per_source: int = 15
) -> List[Dict]:
    """
    Fetch trending topics from all sources and combine them.
    Prioritizes Reddit and HackerNews for better real-time trending content.

    Args:
        markets: Countries for Google Trends
        subreddits: Subreddits to monitor (default: broad coverage)
        limit_per_source: Number of items per source

    Returns:
        Combined and sorted list of trending topics
    """
    logger.info("Fetching trending topics from all sources")

    all_trends = []

    # Prioritize HackerNews and Reddit for real-time trends
    logger.info("Priority: HackerNews and Reddit (real-time trending)")
    hn_trends = fetch_hackernews_top(limit=limit_per_source)
    reddit_trends = fetch_reddit_trending(subreddits=subreddits, limit=limit_per_source)

    # Add Google Trends (may fail, but try anyway)
    google_trends = fetch_google_trends(markets=markets, limit=limit_per_source)

    # Combine with HackerNews and Reddit first (higher priority)
    all_trends.extend(hn_trends)
    all_trends.extend(reddit_trends)
    all_trends.extend(google_trends)

    # Sort by score (descending) - HackerNews/Reddit scores are more reliable
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
    logger.info(f"Sources: HackerNews={len(hn_trends)}, Reddit={len(reddit_trends)}, Google={len(google_trends)}")

    return unique_trends


if __name__ == "__main__":
    # Test the functions
    print("Testing trending topic fetchers...\n")

    print("=== Google Trends ===")
    google_results = fetch_google_trends(markets=['US'], limit=5)
    for trend in google_results:
        print(f"  - {trend['keyword']} (Score: {trend['score']}, Region: {trend['region']})")

    print("\n=== Reddit Trending ===")
    reddit_results = fetch_reddit_trending(subreddits=['technology'], limit=5)
    for trend in reddit_results:
        print(f"  - {trend['keyword'][:60]}... (Score: {trend['score']})")

    print("\n=== HackerNews Top ===")
    hn_results = fetch_hackernews_top(limit=5)
    for trend in hn_results:
        print(f"  - {trend['keyword'][:60]}... (Score: {trend['score']})")

    print("\n=== All Combined ===")
    all_results = get_all_trending_topics(
        markets=['US'],
        subreddits=['technology'],
        limit_per_source=3
    )
    for trend in all_results[:10]:
        print(f"  - {trend['keyword'][:60]}... (Source: {trend['source']}, Score: {trend['score']})")
