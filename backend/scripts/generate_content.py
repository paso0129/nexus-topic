"""
Content Generator using Claude AI

Generates SEO-optimized blog articles using Anthropic's Claude API.
"""

import logging
import os
import re
from typing import Dict, Optional
from datetime import datetime

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_reading_time(text: str, words_per_minute: int = 200) -> int:
    """
    Calculate estimated reading time for text.

    Args:
        text: Article text (HTML or plain text)
        words_per_minute: Average reading speed

    Returns:
        Reading time in minutes
    """
    # Remove HTML tags for accurate word count
    clean_text = re.sub(r'<[^>]+>', '', text)
    word_count = len(clean_text.split())
    reading_time = max(1, round(word_count / words_per_minute))
    return reading_time


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """
    Extract potential keywords from content.

    Args:
        content: Article content
        max_keywords: Maximum number of keywords to return

    Returns:
        List of keywords
    """
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', content)

    # Simple keyword extraction (you might want to use NLP libraries for better results)
    words = re.findall(r'\b[a-z]{4,}\b', clean_text.lower())

    # Count word frequency
    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1

    # Get top keywords
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]

    return keywords


def generate_article(
    topic: str,
    min_words: int = 1500,
    max_words: int = 2000,
    target_audience: str = "North American and European readers",
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict:
    """
    Generate a complete SEO-optimized article using Claude AI.

    Args:
        topic: Topic or keyword to write about
        min_words: Minimum word count
        max_words: Maximum word count
        target_audience: Target reader demographic
        model: Claude model to use

    Returns:
        Dictionary containing:
        {
            'title': str,
            'meta_description': str,
            'content': str (HTML),
            'keywords': List[str],
            'reading_time': int,
            'word_count': int,
            'timestamp': str
        }
    """
    if Anthropic is None:
        logger.error("anthropic package is not installed. Install with: pip install anthropic")
        return {}

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        return {}

    logger.info(f"Generating article about: {topic}")
    logger.info(f"Target length: {min_words}-{max_words} words")

    try:
        client = Anthropic(api_key=api_key)

        # Create detailed prompt for Claude
        prompt = f"""Write a comprehensive, SEO-optimized blog article about: {topic}

Requirements:
- Target audience: {target_audience}
- Word count: {min_words}-{max_words} words
- Format: HTML with proper semantic tags (h2, h3, p, ul, ol, strong, em)
- Style: Informative, engaging, and authoritative
- SEO: Include relevant keywords naturally throughout
- Structure: Introduction, main body with subheadings, conclusion
- Tone: Professional yet accessible

The article should:
1. Start with an engaging introduction that hooks the reader
2. Use clear H2 and H3 headings for structure
3. Include specific examples and data when relevant
4. Provide actionable insights
5. End with a strong conclusion that summarizes key points

Format the output as HTML. Use <h2> for main sections, <h3> for subsections, <p> for paragraphs, <ul>/<ol> for lists.
Do NOT include <html>, <head>, or <body> tags - just the article content.

Also provide:
- A compelling SEO title (under 60 characters)
- A meta description (under 160 characters)

Format your response as:
TITLE: [Your title here]
META: [Your meta description here]
CONTENT:
[Your HTML content here]
"""

        # Call Claude API
        logger.info("Calling Claude API...")
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract response
        response_text = message.content[0].text

        # Parse the response
        title_match = re.search(r'TITLE:\s*(.+?)(?:\n|META:)', response_text, re.IGNORECASE)
        meta_match = re.search(r'META:\s*(.+?)(?:\n|CONTENT:)', response_text, re.IGNORECASE)
        content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.IGNORECASE | re.DOTALL)

        if not all([title_match, meta_match, content_match]):
            logger.error("Failed to parse Claude response properly")
            # Fallback: use entire response as content
            title = topic
            meta_description = f"Learn about {topic}"
            content = response_text
        else:
            title = title_match.group(1).strip()
            meta_description = meta_match.group(1).strip()
            content = content_match.group(1).strip()

        # Calculate metrics
        word_count = len(re.sub(r'<[^>]+>', '', content).split())
        reading_time = calculate_reading_time(content)
        keywords = extract_keywords(content)

        article = {
            'title': title,
            'meta_description': meta_description,
            'content': content,
            'keywords': keywords,
            'reading_time': reading_time,
            'word_count': word_count,
            'timestamp': datetime.now().isoformat(),
            'topic': topic
        }

        logger.info(f"Article generated successfully")
        logger.info(f"Title: {title}")
        logger.info(f"Word count: {word_count}")
        logger.info(f"Reading time: {reading_time} minutes")

        return article

    except Exception as e:
        logger.error(f"Error generating article: {str(e)}")
        return {}


def generate_multiple_articles(
    topics: list,
    articles_count: int = 3,
    **kwargs
) -> list:
    """
    Generate multiple articles from a list of topics with duplicate checking.

    Args:
        topics: List of topic dictionaries from fetch_trending
        articles_count: Number of articles to generate
        **kwargs: Additional arguments to pass to generate_article

    Returns:
        List of article dictionaries
    """
    logger.info(f"Generating {articles_count} articles from {len(topics)} topics")

    # Get existing articles to avoid duplicates
    existing_titles = set()
    try:
        from database import get_db_client, is_supabase_enabled
        if is_supabase_enabled():
            db = get_db_client()
            existing_articles = db.list_articles(limit=100, published_only=False)
            existing_titles = {a.get('title', '').lower() for a in existing_articles}
            logger.info(f"Loaded {len(existing_titles)} existing article titles for duplicate check")
    except Exception as e:
        logger.warning(f"Could not load existing articles: {str(e)}")

    articles = []
    used_topics = set()
    topic_index = 0

    while len(articles) < articles_count and topic_index < len(topics):
        topic_data = topics[topic_index]
        topic = topic_data.get('keyword', topic_data.get('title', 'Unknown Topic'))
        topic_index += 1

        # Skip if topic already used
        if topic.lower() in used_topics:
            logger.info(f"Skipping duplicate topic: {topic}")
            continue

        # Skip if very similar title exists
        topic_lower = topic.lower()
        is_duplicate = False
        for existing_title in existing_titles:
            # Check for exact match or high similarity
            if topic_lower in existing_title or existing_title in topic_lower:
                logger.info(f"Skipping similar topic (already exists): {topic}")
                is_duplicate = True
                break

        if is_duplicate:
            continue

        logger.info(f"Generating article {len(articles)+1}/{articles_count}: {topic}")

        article = generate_article(topic, **kwargs)

        if article:
            # Add source information
            article['source_data'] = topic_data
            articles.append(article)
            used_topics.add(topic.lower())
            existing_titles.add(article['title'].lower())
        else:
            logger.warning(f"Failed to generate article for: {topic}")

    logger.info(f"Successfully generated {len(articles)} unique articles")

    return articles


if __name__ == "__main__":
    # Test the content generation
    print("Testing content generation...\n")

    test_topic = "Artificial Intelligence in Healthcare"

    print(f"Generating article about: {test_topic}")
    article = generate_article(
        topic=test_topic,
        min_words=500,  # Shorter for testing
        max_words=800
    )

    if article:
        print("\n=== Generated Article ===")
        print(f"Title: {article['title']}")
        print(f"Meta: {article['meta_description']}")
        print(f"Word Count: {article['word_count']}")
        print(f"Reading Time: {article['reading_time']} minutes")
        print(f"Keywords: {', '.join(article['keywords'][:5])}")
        print(f"\nContent Preview (first 200 chars):")
        print(article['content'][:200] + "...")
    else:
        print("Failed to generate article")
