"""
Supabase Database Client
Handles all database operations for article storage and retrieval
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseClient:
    """Supabase database client with retry logic and error handling"""

    def __init__(self):
        """Initialize Supabase client from environment variables"""
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "Missing Supabase credentials. Please set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY environment variables."
            )

        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.max_retries = 3
        self.retry_delay = 1  # seconds

        logger.info("Supabase client initialized successfully")

    def _retry_operation(self, operation, *args, **kwargs) -> Any:
        """Execute operation with exponential backoff retry logic"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except APIError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Database operation failed (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {delay}s... Error: {str(e)}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Database operation failed after {self.max_retries} attempts")
            except Exception as e:
                logger.error(f"Unexpected error in database operation: {str(e)}")
                raise

        raise last_exception

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            # Try to query articles table
            result = self.client.table('articles').select('id').limit(1).execute()
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False

    def create_article(
        self,
        slug: str,
        title: str,
        content: str,
        meta_description: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        reading_time: int = 5,
        word_count: int = 0,
        topic: Optional[str] = None,
        published: bool = True,
        featured_image: Optional[str] = None,
        image_attribution: Optional[Dict[str, str]] = None,
        author: Optional[Dict[str, str]] = None,
        source_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new article in the database

        Args:
            slug: URL-friendly article identifier
            title: Article title
            content: Article content (HTML)
            meta_description: SEO meta description
            keywords: List of keywords
            reading_time: Estimated reading time in minutes
            word_count: Number of words in content
            topic: Article topic/category
            published: Whether article is published
            featured_image: URL to featured image
            image_attribution: Unsplash photographer attribution dict
            author: Author information dict
            source_data: Trending source information dict

        Returns:
            Created article dict or None on failure
        """
        try:
            # Prepare article data
            article_data = {
                'slug': slug,
                'title': title,
                'content': content,
                'meta_description': meta_description,
                'keywords': keywords or [],
                'reading_time': reading_time,
                'word_count': word_count,
                'topic': topic,
                'published': published,
                'featured_image': featured_image,
                'image_attribution': image_attribution or {},
                'author': author or {
                    'name': 'NexusTopic Editorial Team',
                    'bio': 'Delivering the latest trending topics and insights'
                }
            }

            # Insert article
            def insert_article():
                return self.client.table('articles').insert(article_data).execute()

            result = self._retry_operation(insert_article)

            if not result.data:
                logger.error("Article creation returned no data")
                return None

            article = result.data[0]
            article_id = article['id']
            logger.info(f"Article created successfully: {slug} (ID: {article_id})")

            # Insert trending source data if provided
            if source_data and article_id:
                try:
                    source_record = {
                        'article_id': article_id,
                        'keyword': source_data.get('keyword', ''),
                        'source': source_data.get('source', 'google_trends'),
                        'score': source_data.get('score', 0),
                        'region': source_data.get('region', 'US'),
                        'url': source_data.get('url'),
                        'timestamp': source_data.get('timestamp', datetime.utcnow().isoformat())
                    }

                    def insert_source():
                        return self.client.table('trending_sources').insert(source_record).execute()

                    self._retry_operation(insert_source)
                    logger.info(f"Trending source data added for article: {slug}")
                except Exception as e:
                    logger.warning(f"Failed to insert trending source data: {str(e)}")
                    # Don't fail the whole operation if source insertion fails

            return article

        except Exception as e:
            logger.error(f"Failed to create article '{slug}': {str(e)}")
            return None

    def get_article_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Get article by slug

        Args:
            slug: Article slug

        Returns:
            Article dict or None if not found
        """
        try:
            def fetch_article():
                return self.client.table('articles').select('*').eq('slug', slug).execute()

            result = self._retry_operation(fetch_article)

            if not result.data:
                logger.warning(f"Article not found: {slug}")
                return None

            article = result.data[0]

            # Fetch associated trending source data
            try:
                def fetch_source():
                    return self.client.table('trending_sources')\
                        .select('*')\
                        .eq('article_id', article['id'])\
                        .execute()

                source_result = self._retry_operation(fetch_source)
                if source_result.data:
                    article['source_data'] = source_result.data[0]
            except Exception as e:
                logger.warning(f"Failed to fetch source data for {slug}: {str(e)}")

            return article

        except Exception as e:
            logger.error(f"Failed to get article '{slug}': {str(e)}")
            return None

    def list_articles(
        self,
        limit: int = 10,
        offset: int = 0,
        published_only: bool = True,
        order_by: str = 'created_at',
        ascending: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List articles with pagination

        Args:
            limit: Number of articles to return
            offset: Number of articles to skip
            published_only: Only return published articles
            order_by: Field to order by
            ascending: Sort order (False = descending)

        Returns:
            List of article dicts
        """
        try:
            def fetch_articles():
                query = self.client.table('articles').select('*')

                if published_only:
                    query = query.eq('published', True)

                query = query.order(order_by, desc=not ascending)
                query = query.range(offset, offset + limit - 1)

                return query.execute()

            result = self._retry_operation(fetch_articles)

            logger.info(f"Listed {len(result.data)} articles (offset={offset}, limit={limit})")
            return result.data

        except Exception as e:
            logger.error(f"Failed to list articles: {str(e)}")
            return []

    def check_slug_exists(self, slug: str) -> bool:
        """
        Check if article with slug already exists

        Args:
            slug: Article slug to check

        Returns:
            True if exists, False otherwise
        """
        try:
            def check_slug():
                return self.client.table('articles')\
                    .select('id')\
                    .eq('slug', slug)\
                    .execute()

            result = self._retry_operation(check_slug)
            exists = len(result.data) > 0

            if exists:
                logger.info(f"Slug already exists: {slug}")

            return exists

        except Exception as e:
            logger.error(f"Failed to check slug '{slug}': {str(e)}")
            return False

    def update_article(
        self,
        slug: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an article

        Args:
            slug: Article slug
            updates: Dict of fields to update

        Returns:
            Updated article dict or None on failure
        """
        try:
            def update_op():
                return self.client.table('articles')\
                    .update(updates)\
                    .eq('slug', slug)\
                    .execute()

            result = self._retry_operation(update_op)

            if not result.data:
                logger.error(f"Failed to update article: {slug}")
                return None

            logger.info(f"Article updated successfully: {slug}")
            return result.data[0]

        except Exception as e:
            logger.error(f"Failed to update article '{slug}': {str(e)}")
            return None

    def delete_article(self, slug: str) -> bool:
        """
        Delete an article

        Args:
            slug: Article slug

        Returns:
            True if deleted, False otherwise
        """
        try:
            def delete_op():
                return self.client.table('articles')\
                    .delete()\
                    .eq('slug', slug)\
                    .execute()

            self._retry_operation(delete_op)
            logger.info(f"Article deleted successfully: {slug}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete article '{slug}': {str(e)}")
            return False

    def list_trending_keywords(self, limit: int = 200) -> List[str]:
        """
        List recent trending keywords from the trending_sources table.

        Args:
            limit: Maximum number of keywords to return

        Returns:
            List of keyword strings
        """
        try:
            def fetch_keywords():
                return self.client.table('trending_sources') \
                    .select('keyword') \
                    .order('timestamp', desc=True) \
                    .limit(limit) \
                    .execute()

            result = self._retry_operation(fetch_keywords)
            keywords = [r['keyword'] for r in result.data]
            logger.info(f"Loaded {len(keywords)} trending keywords")
            return keywords

        except Exception as e:
            logger.error(f"Failed to list trending keywords: {str(e)}")
            return []

    def list_articles_without_images(self) -> List[Dict[str, Any]]:
        """
        List published articles that have no featured_image set.

        Returns:
            List of article dicts missing featured images
        """
        try:
            def fetch_articles():
                return self.client.table('articles') \
                    .select('*') \
                    .eq('published', True) \
                    .or_('featured_image.is.null,featured_image.eq.') \
                    .execute()

            result = self._retry_operation(fetch_articles)
            logger.info(f"Found {len(result.data)} articles without images")
            return result.data

        except Exception as e:
            logger.error(f"Failed to list articles without images: {str(e)}")
            return []

    def get_article_count(self, published_only: bool = True) -> int:
        """
        Get total count of articles

        Args:
            published_only: Only count published articles

        Returns:
            Total article count
        """
        try:
            def count_articles():
                query = self.client.table('articles').select('id', count='exact')

                if published_only:
                    query = query.eq('published', True)

                return query.execute()

            result = self._retry_operation(count_articles)
            count = result.count if hasattr(result, 'count') else len(result.data)

            logger.info(f"Article count: {count}")
            return count

        except Exception as e:
            logger.error(f"Failed to get article count: {str(e)}")
            return 0


# Singleton instance
_db_client: Optional[DatabaseClient] = None


def get_db_client() -> DatabaseClient:
    """Get or create singleton database client instance"""
    global _db_client

    if _db_client is None:
        _db_client = DatabaseClient()

    return _db_client


def is_supabase_enabled() -> bool:
    """Check if Supabase is enabled via environment variable"""
    return os.getenv('USE_SUPABASE', 'false').lower() == 'true'


if __name__ == '__main__':
    # Test database connection
    from dotenv import load_dotenv
    load_dotenv()

    if not is_supabase_enabled():
        print("Supabase is not enabled. Set USE_SUPABASE=true in .env")
        exit(1)

    try:
        db = get_db_client()

        if db.test_connection():
            print("✓ Database connection successful")

            # Get article count
            count = db.get_article_count()
            print(f"✓ Total articles: {count}")
        else:
            print("✗ Database connection failed")
            exit(1)

    except Exception as e:
        print(f"✗ Error: {str(e)}")
        exit(1)
