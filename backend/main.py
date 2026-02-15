#!/usr/bin/env python3
"""
AdSense Blog Automation - Main Entry Point

Orchestrates the complete workflow:
1. Fetch trending topics
2. Generate SEO-optimized content
3. Optimize with AdSense placement
4. Save to JSON for Next.js frontend
"""

import argparse
import logging
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv

from scripts.fetch_trending import get_all_trending_topics
from scripts.generate_content import generate_multiple_articles
from scripts.optimize_adsense import optimize_ad_placement, validate_adsense_config
from scripts.save_article import save_multiple_articles
from scripts.fetch_images import fetch_images_for_articles
from scripts.reclassify import classify_articles

# Import database utilities
try:
    from scripts.database import get_db_client, is_supabase_enabled
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available. Will use JSON-only mode.")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'automation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def validate_environment() -> None:
    """
    Validate environment variables and database connection.
    Checks for required API keys and Supabase configuration.
    """
    import os

    logger.info("\nValidating environment...")

    # Check Gemini CLI availability
    import shutil
    if shutil.which('gemini'):
        logger.info("✓ Gemini CLI found")
    elif os.getenv('GOOGLE_API_KEY'):
        logger.info("✓ Google API key found (Gemini CLI not available, using API)")
    else:
        logger.error("Neither Gemini CLI nor GOOGLE_API_KEY available")
        sys.exit(1)

    # Check Supabase configuration
    if SUPABASE_AVAILABLE and is_supabase_enabled():
        logger.info("✓ Supabase enabled")

        # Check required environment variables
        if not os.getenv('SUPABASE_URL'):
            logger.error("SUPABASE_URL not set in environment")
            sys.exit(1)

        if not os.getenv('SUPABASE_SERVICE_KEY'):
            logger.error("SUPABASE_SERVICE_KEY not set in environment")
            sys.exit(1)

        logger.info("✓ Supabase credentials found")

        # Test database connection
        try:
            db = get_db_client()
            if db.test_connection():
                logger.info("✓ Database connection successful")
                article_count = db.get_article_count()
                logger.info(f"✓ Current articles in database: {article_count}")
            else:
                logger.error("Database connection failed")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            sys.exit(1)
    else:
        logger.info("⊘ Supabase not enabled, using JSON-only mode")

    # Check Gemini image generation capability
    _can_generate_images = os.getenv('GOOGLE_API_KEY') is not None
    try:
        from google import genai as _genai_check
        _can_generate_images = _can_generate_images and True
    except ImportError:
        _can_generate_images = False

    if _can_generate_images:
        logger.info("✓ Gemini image generation available (google-genai + API key)")
    else:
        logger.info("⊘ Gemini image generation not available (needs google-genai + GOOGLE_API_KEY)")

    # Check Unsplash API key (fallback images)
    if os.getenv('UNSPLASH_ACCESS_KEY'):
        logger.info("✓ Unsplash API key found (fallback images)")
    else:
        logger.info("⊘ Unsplash API key not set (fallback images disabled)")

    logger.info("Environment validation complete\n")


def load_config(config_path: str = 'config.yaml') -> Dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config file: {e}")
        sys.exit(1)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='AdSense Blog Automation System with Next.js',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and save 3 articles
  python main.py --articles 3

  # Generate without AdSense optimization
  python main.py --no-adsense --articles 2

  # Use specific markets
  python main.py --markets US UK --articles 2
        """
    )

    parser.add_argument(
        '--articles',
        type=int,
        default=5,
        help='Number of articles to generate (default: 5)'
    )

    parser.add_argument(
        '--markets',
        nargs='+',
        help='Target markets for trending topics (e.g., US UK CA)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    parser.add_argument(
        '--no-adsense',
        action='store_true',
        help='Skip AdSense ad insertion'
    )

    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Skip Unsplash image fetching'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='../frontend/public/articles',
        help='Output directory for articles (default: ../frontend/public/articles)'
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("AdSense Blog Automation System (Next.js)")
    logger.info("=" * 80)
    logger.info(f"Articles to generate: {args.articles}")
    logger.info(f"Unsplash images: {not args.no_images}")
    logger.info(f"AdSense optimization: {not args.no_adsense}")
    logger.info(f"Output directory: {args.output}")
    logger.info("=" * 80)

    # Validate environment
    validate_environment()

    # Load configuration
    config = load_config(args.config)

    # Override markets if specified
    if args.markets:
        config['automation']['target_markets'] = args.markets

    # STEP 1: Fetch Trending Topics
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Fetching Trending Topics")
    logger.info("=" * 80)

    try:
        topics = get_all_trending_topics(
            markets=config['automation']['target_markets'],
            subreddits=config['automation'].get('subreddits', ['technology', 'worldnews']),
            limit_per_source=10
        )

        if not topics:
            logger.error("No trending topics found. Exiting.")
            sys.exit(1)

        logger.info(f"\nTop 10 trending topics:")
        for i, topic in enumerate(topics[:10], 1):
            logger.info(f"  {i}. {topic['keyword'][:60]}... (Source: {topic['source']}, Score: {topic['score']})")

    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
        sys.exit(1)

    # STEP 2: Generate Articles
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Generating Articles with Gemini")
    logger.info("=" * 80)

    try:
        articles = generate_multiple_articles(
            topics=topics,
            articles_count=args.articles,
            min_words=config['automation'].get('min_words', 1500),
            max_words=config['automation'].get('max_words', 2000)
        )

        if not articles:
            logger.error("No articles generated. Exiting.")
            sys.exit(1)

        logger.info(f"\nSuccessfully generated {len(articles)} articles:")
        for i, article in enumerate(articles, 1):
            logger.info(f"  {i}. {article['title']} ({article['word_count']} words)")

    except Exception as e:
        logger.error(f"Error generating articles: {e}")
        sys.exit(1)

    # STEP 2.5: Verify & Correct Categories
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2.5: Verifying Article Categories with Gemini")
    logger.info("=" * 80)

    try:
        articles = classify_articles(articles)
        logger.info("✓ Category verification complete")
    except Exception as e:
        logger.warning(f"Category verification failed: {e}")
        logger.warning("Continuing with original categories...")

    # STEP 2.6: Fetch Unsplash Cover Images
    if not args.no_images:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2.6: Generating Cover Images (Gemini AI + Unsplash fallback)")
        logger.info("=" * 80)

        try:
            articles = fetch_images_for_articles(articles)
            images_found = sum(1 for a in articles if a.get('featured_image'))
            logger.info(f"✓ Images fetched: {images_found}/{len(articles)} articles have cover images")
        except Exception as e:
            logger.warning(f"Error fetching images: {e}")
            logger.warning("Continuing without cover images...")
    else:
        logger.info("\n⊘ Skipping image generation (--no-images flag)")

    # STEP 3: Optimize with AdSense
    if not args.no_adsense:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Optimizing AdSense Placement")
        logger.info("=" * 80)

        try:
            adsense_config = config.get('adsense', {})

            if validate_adsense_config(adsense_config):
                for i, article in enumerate(articles, 1):
                    logger.info(f"Optimizing article {i}/{len(articles)}: {article['title']}")

                    optimized_content = optimize_ad_placement(
                        article['content'],
                        adsense_config
                    )

                    article['content'] = optimized_content

                logger.info(f"✓ All articles optimized with AdSense ads")
            else:
                logger.warning("Invalid AdSense config. Skipping ad insertion.")

        except Exception as e:
            logger.error(f"Error optimizing AdSense: {e}")
            logger.warning("Continuing without ad optimization...")
    else:
        logger.info("\n⊘ Skipping AdSense optimization (--no-adsense flag)")

    # STEP 4: Save Articles
    logger.info("\n" + "=" * 80)
    if SUPABASE_AVAILABLE and is_supabase_enabled():
        logger.info("STEP 4: Saving Articles to Database and JSON")
    else:
        logger.info("STEP 4: Saving Articles to JSON")
    logger.info("=" * 80)

    try:
        results = save_multiple_articles(
            articles=articles,
            output_dir=args.output
        )

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SAVE SUMMARY")
        logger.info("=" * 80)

        success_count = sum(1 for r in results if r['success'])
        logger.info(f"Total articles: {len(results)}")
        logger.info(f"Successfully saved: {success_count}")
        logger.info(f"Failed: {len(results) - success_count}")

        logger.info("\nSaved articles:")
        for i, result in enumerate(results, 1):
            status_icon = "✓" if result['success'] else "✗"
            path = result['path'] if result['success'] else "Failed"
            logger.info(f"  {status_icon} {i}. {result['title']}")
            logger.info(f"     Slug: {result['slug']}")
            logger.info(f"     Path: {path}")

    except Exception as e:
        logger.error(f"Error saving articles: {e}")
        sys.exit(1)

    # Final Summary
    logger.info("\n" + "=" * 80)
    logger.info("AUTOMATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Articles saved to: {args.output}")
    logger.info("Next steps:")
    logger.info("  1. cd frontend")
    logger.info("  2. npm run dev")
    logger.info("  3. Open http://localhost:3000")
    logger.info("\nTo deploy:")
    logger.info("  1. git add .")
    logger.info("  2. git commit -m 'Add articles'")
    logger.info("  3. git push")
    logger.info("  4. Vercel will auto-deploy")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\nProcess interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
