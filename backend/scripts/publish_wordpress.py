"""
WordPress Publisher

Publishes articles to WordPress using REST API with secure authentication.
"""

import logging
import os
from typing import Dict, Optional, List
from datetime import datetime
import base64

import requests
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WordPressPublisher:
    """WordPress REST API client for publishing articles."""

    def __init__(
        self,
        site_url: str,
        username: Optional[str] = None,
        app_password: Optional[str] = None
    ):
        """
        Initialize WordPress publisher.

        Args:
            site_url: WordPress site URL (e.g., https://yourblog.com)
            username: WordPress username (from env if not provided)
            app_password: WordPress application password (from env if not provided)
        """
        self.site_url = site_url.rstrip('/')
        self.api_url = f"{self.site_url}/wp-json/wp/v2"

        self.username = username or os.getenv('WP_USERNAME')
        self.app_password = app_password or os.getenv('WP_APP_PASSWORD')

        if not self.username or not self.app_password:
            raise ValueError("WordPress credentials not provided")

        # Create authentication token
        credentials = f"{self.username}:{self.app_password}"
        token = base64.b64encode(credentials.encode()).decode()

        self.headers = {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json'
        }

        logger.info(f"WordPress publisher initialized for: {self.site_url}")

    def test_connection(self) -> bool:
        """
        Test connection to WordPress API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(
                f"{self.api_url}/users/me",
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Connected as: {user_data.get('name', 'Unknown')}")
                return True
            else:
                logger.error(f"Connection failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False

    def create_post(
        self,
        title: str,
        content: str,
        status: str = 'publish',
        excerpt: Optional[str] = None,
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None,
        featured_media: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Create a new WordPress post.

        Args:
            title: Post title
            content: Post content (HTML)
            status: Post status ('draft', 'publish', 'pending')
            excerpt: Post excerpt/meta description
            categories: List of category IDs
            tags: List of tag IDs
            featured_media: Featured image media ID

        Returns:
            Post data dictionary or None if failed
        """
        post_data = {
            'title': title,
            'content': content,
            'status': status,
            'excerpt': excerpt or '',
            'format': 'standard'
        }

        if categories:
            post_data['categories'] = categories

        if tags:
            post_data['tags'] = tags

        if featured_media:
            post_data['featured_media'] = featured_media

        try:
            logger.info(f"Creating post: {title}")

            response = requests.post(
                f"{self.api_url}/posts",
                headers=self.headers,
                json=post_data,
                timeout=30
            )

            if response.status_code == 201:
                post = response.json()
                logger.info(f"Post created successfully: {post['link']}")
                return post
            else:
                logger.error(f"Failed to create post: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating post: {str(e)}")
            return None

    def get_categories(self) -> List[Dict]:
        """
        Get all categories from WordPress.

        Returns:
            List of category dictionaries
        """
        try:
            response = requests.get(
                f"{self.api_url}/categories",
                headers=self.headers,
                params={'per_page': 100},
                timeout=10
            )

            if response.status_code == 200:
                categories = response.json()
                logger.info(f"Retrieved {len(categories)} categories")
                return categories
            else:
                logger.error(f"Failed to get categories: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
            return []

    def create_category(self, name: str, description: str = '') -> Optional[int]:
        """
        Create a new category.

        Args:
            name: Category name
            description: Category description

        Returns:
            Category ID or None if failed
        """
        try:
            response = requests.post(
                f"{self.api_url}/categories",
                headers=self.headers,
                json={'name': name, 'description': description},
                timeout=10
            )

            if response.status_code == 201:
                category = response.json()
                logger.info(f"Category created: {name} (ID: {category['id']})")
                return category['id']
            else:
                logger.error(f"Failed to create category: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error creating category: {str(e)}")
            return None

    def get_or_create_category(self, name: str) -> Optional[int]:
        """
        Get category ID by name, or create if doesn't exist.

        Args:
            name: Category name

        Returns:
            Category ID or None
        """
        categories = self.get_categories()

        for category in categories:
            if category['name'].lower() == name.lower():
                return category['id']

        # Category doesn't exist, create it
        return self.create_category(name)


def publish_to_wordpress(
    article: Dict,
    wp_config: Dict,
    status: str = 'publish',
    category_name: Optional[str] = None
) -> Optional[str]:
    """
    Publish an article to WordPress.

    Args:
        article: Article dictionary from generate_content
        wp_config: WordPress configuration with url, username, password
        status: Post status ('draft', 'publish', 'pending')
        category_name: Optional category name to assign

    Returns:
        Published post URL or None if failed
    """
    try:
        # Initialize publisher
        publisher = WordPressPublisher(
            site_url=wp_config['url'],
            username=wp_config.get('username'),
            app_password=wp_config.get('app_password')
        )

        # Test connection
        if not publisher.test_connection():
            logger.error("Failed to connect to WordPress")
            return None

        # Get or create category
        category_ids = None
        if category_name:
            category_id = publisher.get_or_create_category(category_name)
            if category_id:
                category_ids = [category_id]

        # Create post
        post = publisher.create_post(
            title=article['title'],
            content=article['content'],
            excerpt=article.get('meta_description', ''),
            status=status,
            categories=category_ids
        )

        if post:
            logger.info(f"Article published successfully: {post['link']}")
            return post['link']
        else:
            logger.error("Failed to publish article")
            return None

    except Exception as e:
        logger.error(f"Error publishing to WordPress: {str(e)}")
        return None


def publish_multiple_articles(
    articles: List[Dict],
    wp_config: Dict,
    status: str = 'publish',
    delay_between_posts: int = 0
) -> List[Dict]:
    """
    Publish multiple articles to WordPress.

    Args:
        articles: List of article dictionaries
        wp_config: WordPress configuration
        status: Post status for all articles
        delay_between_posts: Seconds to wait between posts (to avoid rate limiting)

    Returns:
        List of results with URLs and statuses
    """
    import time

    results = []

    for i, article in enumerate(articles):
        logger.info(f"Publishing article {i+1}/{len(articles)}: {article['title']}")

        url = publish_to_wordpress(article, wp_config, status=status)

        results.append({
            'title': article['title'],
            'url': url,
            'success': url is not None,
            'timestamp': datetime.now().isoformat()
        })

        if delay_between_posts > 0 and i < len(articles) - 1:
            logger.info(f"Waiting {delay_between_posts} seconds before next post...")
            time.sleep(delay_between_posts)

    success_count = sum(1 for r in results if r['success'])
    logger.info(f"Published {success_count}/{len(articles)} articles successfully")

    return results


if __name__ == "__main__":
    # Test WordPress connection
    print("Testing WordPress publisher...\n")

    # Load config from environment
    wp_url = os.getenv('WP_URL', 'https://yourblog.com')
    wp_username = os.getenv('WP_USERNAME')
    wp_password = os.getenv('WP_APP_PASSWORD')

    if not wp_username or not wp_password:
        print("Please set WP_USERNAME and WP_APP_PASSWORD in .env file")
        exit(1)

    try:
        publisher = WordPressPublisher(wp_url, wp_username, wp_password)

        print("Testing connection...")
        if publisher.test_connection():
            print("✓ Connection successful!\n")

            print("Fetching categories...")
            categories = publisher.get_categories()
            print(f"✓ Found {len(categories)} categories:")
            for cat in categories[:5]:
                print(f"  - {cat['name']} (ID: {cat['id']})")
        else:
            print("✗ Connection failed")

    except Exception as e:
        print(f"Error: {str(e)}")
