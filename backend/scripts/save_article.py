"""
Article Saver

Saves generated articles as JSON files for Next.js frontend.
"""

import logging
import os
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_slug(title: str) -> str:
    """
    Create URL-friendly slug from title.

    Args:
        title: Article title

    Returns:
        URL slug
    """
    # Convert to lowercase
    slug = title.lower()

    # Remove special characters
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)

    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)

    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    return slug


def save_article(
    article: Dict,
    output_dir: str = '../frontend/public/articles'
) -> Optional[str]:
    """
    Save article as JSON file.

    Args:
        article: Article dictionary from generate_content
        output_dir: Directory to save articles

    Returns:
        Path to saved file or None if failed
    """
    try:
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create slug from title
        slug = create_slug(article['title'])

        # Add metadata
        article_data = {
            'slug': slug,
            'title': article['title'],
            'meta_description': article.get('meta_description', ''),
            'content': article['content'],
            'keywords': article.get('keywords', []),
            'reading_time': article.get('reading_time', 5),
            'word_count': article.get('word_count', 0),
            'topic': article.get('topic', ''),
            'created_at': article.get('timestamp', datetime.now().isoformat()),
            'updated_at': datetime.now().isoformat(),
            'published': True,
            'featured_image': article.get('featured_image', ''),
            'author': {
                'name': 'AI Content Generator',
                'bio': 'Automated content powered by Claude AI'
            },
            'source_data': article.get('source_data', {})
        }

        # Save to JSON file
        file_path = output_path / f"{slug}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Article saved: {file_path}")

        return str(file_path)

    except Exception as e:
        logger.error(f"Error saving article: {str(e)}")
        return None


def save_articles_index(
    articles: List[Dict],
    output_dir: str = '../frontend/public/articles'
) -> bool:
    """
    Save articles index file for listing page.

    Args:
        articles: List of article dictionaries
        output_dir: Directory to save index

    Returns:
        True if successful
    """
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Create index data
        index_data = []

        for article in articles:
            slug = create_slug(article['title'])
            index_data.append({
                'slug': slug,
                'title': article['title'],
                'meta_description': article.get('meta_description', ''),
                'reading_time': article.get('reading_time', 5),
                'keywords': article.get('keywords', [])[:5],
                'created_at': article.get('timestamp', datetime.now().isoformat()),
                'topic': article.get('topic', '')
            })

        # Load existing index if it exists
        index_path = output_path / 'index.json'
        existing_index = []

        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                existing_index = json.load(f)

        # Merge with existing (avoid duplicates)
        existing_slugs = {item['slug'] for item in existing_index}
        new_items = [item for item in index_data if item['slug'] not in existing_slugs]

        # Combine and sort by date (newest first)
        combined_index = existing_index + new_items
        combined_index.sort(key=lambda x: x['created_at'], reverse=True)

        # Save index
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(combined_index, f, ensure_ascii=False, indent=2)

        logger.info(f"Articles index updated: {index_path}")
        logger.info(f"Total articles: {len(combined_index)}")

        return True

    except Exception as e:
        logger.error(f"Error saving articles index: {str(e)}")
        return False


def save_multiple_articles(
    articles: List[Dict],
    output_dir: str = '../frontend/public/articles'
) -> List[Dict]:
    """
    Save multiple articles and update index.

    Args:
        articles: List of article dictionaries
        output_dir: Directory to save articles

    Returns:
        List of results with paths and statuses
    """
    results = []

    for i, article in enumerate(articles):
        logger.info(f"Saving article {i+1}/{len(articles)}: {article['title']}")

        file_path = save_article(article, output_dir)

        results.append({
            'title': article['title'],
            'slug': create_slug(article['title']),
            'path': file_path,
            'success': file_path is not None,
            'timestamp': datetime.now().isoformat()
        })

    # Update index
    save_articles_index(articles, output_dir)

    success_count = sum(1 for r in results if r['success'])
    logger.info(f"Saved {success_count}/{len(articles)} articles successfully")

    return results


def get_all_articles(
    articles_dir: str = '../frontend/public/articles'
) -> List[Dict]:
    """
    Load all articles from JSON files.

    Args:
        articles_dir: Directory containing article JSON files

    Returns:
        List of article dictionaries
    """
    try:
        articles_path = Path(articles_dir)

        if not articles_path.exists():
            logger.warning(f"Articles directory not found: {articles_dir}")
            return []

        articles = []

        for json_file in articles_path.glob('*.json'):
            # Skip index file
            if json_file.name == 'index.json':
                continue

            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    article = json.load(f)
                    articles.append(article)
            except Exception as e:
                logger.error(f"Error loading {json_file}: {str(e)}")
                continue

        # Sort by date (newest first)
        articles.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        logger.info(f"Loaded {len(articles)} articles")

        return articles

    except Exception as e:
        logger.error(f"Error loading articles: {str(e)}")
        return []


if __name__ == "__main__":
    # Test the save functionality
    print("Testing article save functionality...\n")

    # Sample article
    test_article = {
        'title': 'Test Article: Introduction to AI',
        'meta_description': 'Learn about artificial intelligence basics',
        'content': '<h2>Introduction</h2><p>This is a test article about AI.</p>',
        'keywords': ['AI', 'machine learning', 'technology'],
        'reading_time': 5,
        'word_count': 500,
        'topic': 'Artificial Intelligence',
        'timestamp': datetime.now().isoformat()
    }

    # Save article
    print("Saving test article...")
    file_path = save_article(test_article, output_dir='./test_output')

    if file_path:
        print(f"✓ Article saved: {file_path}")

        # Create slug
        slug = create_slug(test_article['title'])
        print(f"✓ Slug: {slug}")

        # Update index
        print("\nUpdating index...")
        save_articles_index([test_article], output_dir='./test_output')
        print("✓ Index updated")

        # Load articles
        print("\nLoading articles...")
        articles = get_all_articles('./test_output')
        print(f"✓ Loaded {len(articles)} articles")
    else:
        print("✗ Failed to save article")
