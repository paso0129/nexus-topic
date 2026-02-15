"""
Article Cover Image Provider

Priority:
  1. Gemini AI image generation (gemini-2.5-flash-image) → Supabase Storage
  2. Unsplash search (fallback)
  3. Category thumbnail (final fallback, handled by frontend)
"""

import io
import os
import re
import time
import uuid
import logging
import subprocess
import shutil
from typing import Dict, List, Optional

import requests

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from google import genai as genai_new
    from google.genai import types as genai_types
except ImportError:
    genai_new = None
    genai_types = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from supabase import create_client
except ImportError:
    create_client = None

logger = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
STORAGE_BUCKET = "article-images"

_gemini_cli_path = shutil.which('gemini')


# ---------------------------------------------------------------------------
# Gemini AI Image Generation
# ---------------------------------------------------------------------------

def _build_image_prompt(article: Dict) -> str:
    """Build a prompt for Gemini image generation from article metadata."""
    title = article.get('title', '')
    topic = article.get('topic', '')
    description = article.get('meta_description', '')

    return (
        f"Generate a high-quality, photorealistic editorial cover image for a news article.\n"
        f"Title: {title}\n"
        f"Topic: {topic}\n"
        f"Description: {description}\n\n"
        f"Requirements:\n"
        f"- Landscape orientation (16:9 aspect ratio)\n"
        f"- Clean, professional editorial style suitable for a news website\n"
        f"- No text, watermarks, logos, or UI elements in the image\n"
        f"- Vibrant but natural colors\n"
        f"- Focus on the core visual concept of the article topic"
    )


def _get_supabase_client():
    """Create a Supabase client for storage operations."""
    if not create_client:
        return None
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    if not url or not key:
        return None
    return create_client(url, key)


def _ensure_storage_bucket(supabase_client) -> bool:
    """Ensure the article-images storage bucket exists (public)."""
    try:
        supabase_client.storage.get_bucket(STORAGE_BUCKET)
        return True
    except Exception:
        pass
    try:
        supabase_client.storage.create_bucket(
            STORAGE_BUCKET,
            options={"public": True},
        )
        logger.info(f"Created storage bucket: {STORAGE_BUCKET}")
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            return True
        logger.error(f"Failed to create storage bucket: {e}")
        return False


def _upload_to_supabase_storage(image_bytes: bytes, filename: str) -> Optional[str]:
    """Upload image bytes to Supabase Storage and return the public URL."""
    client = _get_supabase_client()
    if not client:
        logger.warning("Supabase client not available for storage upload")
        return None

    if not _ensure_storage_bucket(client):
        return None

    try:
        client.storage.from_(STORAGE_BUCKET).upload(
            path=filename,
            file=image_bytes,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
        public_url = client.storage.from_(STORAGE_BUCKET).get_public_url(filename)
        logger.info(f"  Uploaded to Supabase Storage: {filename}")
        return public_url
    except Exception as e:
        logger.error(f"Supabase Storage upload failed: {e}")
        return None


def generate_gemini_image(article: Dict) -> Optional[str]:
    """
    Generate a cover image using Gemini 2.5 Flash Image model.
    Returns the public URL from Supabase Storage, or None on failure.
    """
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        logger.info("  GOOGLE_API_KEY not set, skipping Gemini image generation")
        return None

    if not genai_new or not genai_types:
        logger.info("  google-genai SDK not installed, skipping Gemini image generation")
        return None

    if not Image:
        logger.warning("  Pillow not installed, skipping Gemini image generation")
        return None

    prompt = _build_image_prompt(article)

    try:
        client = genai_new.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image from response
        if not response.candidates:
            logger.warning("  Gemini returned no candidates")
            return None

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_data = part.inline_data.data
                # Convert to PNG via Pillow for consistency
                img = Image.open(io.BytesIO(image_data))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()

                slug = article.get('slug', uuid.uuid4().hex[:12])
                filename = f"{slug}.png"
                public_url = _upload_to_supabase_storage(png_bytes, filename)
                if public_url:
                    logger.info(f"  -> AI image generated and uploaded ({len(png_bytes)//1024}KB)")
                    return public_url

        logger.warning("  Gemini response contained no image data")
        return None

    except Exception as e:
        logger.warning(f"  Gemini image generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Unsplash Fallback (existing logic)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main orchestrator: Gemini first → Unsplash fallback
# ---------------------------------------------------------------------------

def fetch_images_for_articles(articles: List[Dict]) -> List[Dict]:
    """
    Fetch cover images for articles.
    Priority: Gemini AI generation → Unsplash search → category thumbnail (frontend).
    """
    gemini_ok = 0
    unsplash_ok = 0

    for i, article in enumerate(articles):
        if article.get('featured_image'):
            logger.info(f"Article {i+1}/{len(articles)} already has featured image, skipping")
            continue

        title_short = article.get('title', '')[:60]
        logger.info(f"Image {i+1}/{len(articles)}: {title_short}...")

        # --- 1) Try Gemini AI image generation ---
        gemini_url = generate_gemini_image(article)
        if gemini_url:
            article['featured_image'] = gemini_url
            article['image_attribution'] = {
                'source': 'gemini',
                'model': 'gemini-2.5-flash-image',
            }
            gemini_ok += 1
            continue

        # --- 2) Fallback to Unsplash ---
        logger.info(f"  Gemini failed, falling back to Unsplash...")
        query = _build_search_query(article)
        logger.info(f"  Unsplash query: '{query}'")

        result = fetch_unsplash_image(query)
        if result:
            article['featured_image'] = result['url']
            article['image_attribution'] = {
                'source': 'unsplash',
                'photographer_name': result['photographer_name'],
                'photographer_url': result['photographer_url'],
                'unsplash_url': result['unsplash_url'],
            }
            unsplash_ok += 1
            logger.info(f"  -> Unsplash image by {result['photographer_name']}")
        else:
            logger.info(f"  -> No image found, article will use category thumbnail")

        if i < len(articles) - 1:
            time.sleep(1.0)

    logger.info(f"Image summary: {gemini_ok} AI-generated, {unsplash_ok} Unsplash, "
                f"{len(articles) - gemini_ok - unsplash_ok} no image")
    return articles
