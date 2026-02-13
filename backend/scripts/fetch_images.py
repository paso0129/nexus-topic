"""
Unsplash Image Fetcher

Fetches cover images from Unsplash API based on article keywords/topic.
Uses Gemini to generate visually descriptive search queries for better relevance.
Follows Unsplash API guidelines: https://unsplash.com/documentation
"""

import os
import re
import time
import logging
import subprocess
import shutil
from typing import Dict, List, Optional

import requests

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

_gemini_cli_path = shutil.which('gemini')


def _build_search_query_with_ai(article: Dict) -> Optional[str]:
    """
    Use Gemini to generate a visually descriptive Unsplash search query.
    Tries API first, falls back to CLI.
    """
    title = article.get('title', '')
    description = article.get('meta_description', '')
    topic = article.get('topic', '')

    prompt = (
        f"Generate a short Unsplash image search query (2-4 words) that would find "
        f"a visually relevant photo for this article. Focus on concrete, visual concepts "
        f"(objects, scenes, settings) rather than abstract ideas. Do NOT use brand names, "
        f"proper nouns, or product names - use generic visual descriptions instead.\n\n"
        f"Title: {title}\n"
        f"Topic: {topic}\n"
        f"Description: {description}\n\n"
        f"Reply with ONLY the search query, nothing else."
    )

    # Try Gemini API
    if os.getenv('GOOGLE_API_KEY') and genai:
        try:
            genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
            model = genai.GenerativeModel('gemini-3-flash-preview')
            resp = model.generate_content(prompt)
            query = resp.text.strip().strip('"').strip("'")
            logger.info(f"  AI query: '{query}'")
            return query
        except Exception as e:
            logger.warning(f"Gemini API query generation failed: {e}")

    # Fallback to Gemini CLI
    if _gemini_cli_path:
        try:
            result = subprocess.run(
                [_gemini_cli_path, '-m', 'gemini-2.5-flash', '-p', prompt],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split('\n')
                         if not l.startswith('Loaded cached') and not l.startswith('Hook registry')]
                query = '\n'.join(lines).strip().strip('"').strip("'")
                logger.info(f"  AI query (CLI): '{query}'")
                return query
        except Exception as e:
            logger.warning(f"Gemini CLI query generation failed: {e}")

    return None


def _build_search_query_fallback(article: Dict) -> str:
    """Fallback: build a search query from article title keywords."""
    title = article.get('title', '')

    stop = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'can',
            'may', 'might', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'into', 'its', 'it', 'this',
            'that', 'how', 'why', 'what', 'when', 'who', 'which', 'new', 'not',
            'no', 'vs', 'about', 'after', 'before', 'over', 'out', 'up'}
    words = re.findall(r'[a-zA-Z0-9]+', title)
    key_words = [w for w in words if w.lower() not in stop and len(w) > 2]

    topic = article.get('topic', '')
    parts = key_words[:3]
    if topic and topic.lower() not in [p.lower() for p in parts]:
        parts.append(topic)

    return ' '.join(parts) if parts else title[:50]


def _build_search_query(article: Dict) -> str:
    """Build a search query for Unsplash. Tries AI first, falls back to keywords."""
    ai_query = _build_search_query_with_ai(article)
    if ai_query:
        return ai_query
    return _build_search_query_fallback(article)


def fetch_unsplash_image(query: str) -> Optional[Dict[str, str]]:
    """Fetch a landscape image from Unsplash search API."""
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
                pass

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
    """Fetch Unsplash cover images for a batch of articles."""
    access_key = os.getenv('UNSPLASH_ACCESS_KEY')
    if not access_key:
        logger.warning("UNSPLASH_ACCESS_KEY not set. Skipping image fetch for all articles.")
        return articles

    for i, article in enumerate(articles):
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

        if i < len(articles) - 1:
            time.sleep(1.5)

    return articles
