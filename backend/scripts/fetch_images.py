"""
Unsplash Image Fetcher

Fetches cover images from Unsplash API based on article keywords/topic.
Follows Unsplash API guidelines: https://unsplash.com/documentation
"""

import os
import time
import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"


def _build_search_query(article: Dict) -> str:
    """
    Build a search query from article title and topic.
    Uses title as primary source for better image relevance.

    Args:
        article: Article dictionary with 'title', 'keywords', 'topic' fields

    Returns:
        Search query string
    """
    import re

    title = article.get('title', '')

    # Extract key nouns from title (remove common filler words)
    stop = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'can',
            'may', 'might', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'into', 'its', 'it', 'this',
            'that', 'how', 'why', 'what', 'when', 'who', 'which', 'new', 'not',
            'no', 'vs', 'about', 'after', 'before', 'over', 'out', 'up'}
    words = re.findall(r'[a-zA-Z0-9]+', title)
    key_words = [w for w in words if w.lower() not in stop and len(w) > 2]

    # Use top 4 title words + topic for a focused query
    topic = article.get('topic', '')
    parts = key_words[:4]
    if topic and topic.lower() not in [p.lower() for p in parts]:
        parts.append(topic)

    return ' '.join(parts) if parts else title[:50]


def fetch_unsplash_image(query: str) -> Optional[Dict[str, str]]:
    """
    Fetch a landscape image from Unsplash search API.

    Args:
        query: Search query string

    Returns:
        Dict with url, photographer_name, photographer_url, unsplash_url
        or None on failure
    """
    access_key = os.getenv('UNSPLASH_ACCESS_KEY')
    if not access_key:
        logger.warning("UNSPLASH_ACCESS_KEY not set, skipping image fetch")
        return None

    try:
        response = requests.get(
            UNSPLASH_API_URL,
            params={
                'query': query,
                'orientation': 'landscape',
                'content_filter': 'high',
                'per_page': 1,
            },
            headers={
                'Authorization': f'Client-ID {access_key}',
                'Accept-Version': 'v1',
            },
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        results = data.get('results', [])

        if not results:
            logger.info(f"No Unsplash images found for query: {query}")
            return None

        photo = results[0]
        image_url = photo['urls'].get('regular', photo['urls'].get('small', ''))
        photographer = photo.get('user', {})

        # Trigger download event (Unsplash API guideline requirement)
        download_location = photo.get('links', {}).get('download_location', '')
        if download_location:
            try:
                requests.get(
                    download_location,
                    headers={'Authorization': f'Client-ID {access_key}'},
                    timeout=5,
                )
            except Exception:
                pass  # Non-critical, best-effort

        return {
            'url': image_url,
            'photographer_name': photographer.get('name', 'Unknown'),
            'photographer_url': photographer.get('links', {}).get('html', ''),
            'unsplash_url': photo.get('links', {}).get('html', ''),
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Unsplash API request failed for query '{query}': {e}")
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Error parsing Unsplash response for query '{query}': {e}")
        return None


def fetch_images_for_articles(articles: List[Dict]) -> List[Dict]:
    """
    Fetch Unsplash cover images for a batch of articles.
    Adds featured_image and image_attribution fields to each article dict.

    Respects Unsplash rate limits with a 1.5s delay between requests.

    Args:
        articles: List of article dicts

    Returns:
        Same list with featured_image and image_attribution populated
    """
    access_key = os.getenv('UNSPLASH_ACCESS_KEY')
    if not access_key:
        logger.warning("UNSPLASH_ACCESS_KEY not set. Skipping image fetch for all articles.")
        return articles

    for i, article in enumerate(articles):
        # Skip if article already has a featured image
        if article.get('featured_image'):
            logger.info(f"Article {i+1}/{len(articles)} already has featured image, skipping")
            continue

        query = _build_search_query(article)
        logger.info(f"Fetching image {i+1}/{len(articles)} for query: '{query}'")

        result = fetch_unsplash_image(query)

        if result:
            article['featured_image'] = result['url']
            article['image_attribution'] = {
                'photographer_name': result['photographer_name'],
                'photographer_url': result['photographer_url'],
                'unsplash_url': result['unsplash_url'],
            }
            logger.info(f"  -> Image by {result['photographer_name']}")
        else:
            logger.info(f"  -> No image found, article will use category thumbnail")

        # Rate limit: wait between requests (skip after last)
        if i < len(articles) - 1:
            time.sleep(1.5)

    return articles
