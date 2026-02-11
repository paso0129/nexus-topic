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

# Stopwords to ignore during similarity comparison
_STOPWORDS = frozenset([
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'about', 'between',
    'through', 'after', 'before', 'during', 'and', 'but', 'or', 'not',
    'no', 'nor', 'so', 'yet', 'both', 'either', 'neither', 'each',
    'every', 'all', 'any', 'few', 'more', 'most', 'other', 'some',
    'such', 'than', 'too', 'very', 'just', 'because', 'if', 'when',
    'how', 'what', 'why', 'where', 'who', 'which', 'that', 'this',
    'it', 'its', 'you', 'your', 'we', 'our', 'they', 'their', 'them',
    'he', 'she', 'his', 'her', 'my', 'me', 'up', 'out', 'new',
])


def _is_similar(text_a: str, text_b: str, threshold: float = 0.35) -> bool:
    """
    Check if two texts are similar using word overlap (Jaccard similarity).
    Ignores stopwords but keeps short significant words (e.g. "AI").

    Args:
        text_a: First text (lowercase)
        text_b: Second text (lowercase)
        threshold: Similarity threshold (0.0 to 1.0). Default 0.35 to catch
                   short keyword vs long title comparisons.

    Returns:
        True if similarity >= threshold
    """
    def extract_words(text):
        words = set(re.findall(r'[a-z0-9]+', text))
        return {w for w in words if len(w) > 1 and w not in _STOPWORDS}

    words_a = extract_words(text_a)
    words_b = extract_words(text_b)

    if not words_a or not words_b:
        return False

    intersection = words_a & words_b
    union = words_a | words_b

    similarity = len(intersection) / len(union) if union else 0

    # Also check: if one set is a subset of the other
    if words_a.issubset(words_b) or words_b.issubset(words_a):
        return True

    return similarity >= threshold


def _is_semantic_duplicate(new_title: str, existing_titles: set) -> bool:
    """
    Use Claude Haiku to check if a generated article title covers the same
    topic as any existing article. Catches duplicates that word-overlap
    similarity misses (e.g. 'Ring Surveillance Dragnet' vs
    'Ring Doorbell Network Sparks Privacy Outcry').

    Args:
        new_title: The newly generated article title
        existing_titles: Set of existing article titles (lowercase)

    Returns:
        True if the new title is a semantic duplicate
    """
    try:
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return False

        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)

        # Send top 50 existing titles to keep prompt short
        titles_list = '\n'.join(list(existing_titles)[:50])

        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=5,
            messages=[{
                'role': 'user',
                'content': (
                    f'Does this new article title cover the SAME topic as any existing article?\n\n'
                    f'New title: {new_title}\n\n'
                    f'Existing titles:\n{titles_list}\n\n'
                    f'Reply ONLY "YES" or "NO".'
                ),
            }],
        )
        answer = resp.content[0].text.strip().upper()
        if answer == 'YES':
            logger.info(f"Semantic duplicate detected by Claude: '{new_title}'")
            return True
        return False
    except Exception as e:
        logger.warning(f"Semantic duplicate check failed: {e}")
        return False


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


VALID_CATEGORIES = [
    'AI', 'BIZ & IT', 'CARS', 'CULTURE', 'GAMING', 'HEALTH',
    'POLICY', 'SCIENCE', 'SECURITY', 'SPACE', 'TECH',
]


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
        prompt = f"""Write a comprehensive, trending news article analyzing: {topic}

CRITICAL REQUIREMENTS:
- This is a TRENDING TOPIC right now - explain WHY it's trending and getting so much attention
- Start by explaining what's happening and why people are searching for this topic TODAY
- Include analysis of the trend, public reaction, and implications
- Write as if you're covering breaking news or a hot trending story

Article Requirements:
- Target audience: {target_audience}
- Word count: {min_words}-{max_words} words
- Format: HTML with proper semantic tags (h2, h3, p, ul, ol, strong, em)
- Style: News-style, authoritative, analytical
- SEO: Include relevant keywords naturally throughout
- Tone: Professional journalist covering trending topics

The article MUST include:
1. **Opening Hook**: Explain what's happening right now and why everyone is talking about this
2. **Background Context**: Provide essential background for readers who just heard about this
3. **Trend Analysis**: Analyze WHY this is trending - what triggered the surge in interest?
4. **Key Details**: Cover the most important facts, data, quotes, or developments
5. **Public Reaction**: How are people responding? What are the discussions?
6. **Implications**: What does this mean? Why should readers care?
7. **Conclusion**: Summarize the trend and what to watch for next

Writing Style:
- Write like you're a professional journalist covering today's trending stories
- Be engaging and informative - explain complex topics clearly
- Use present tense for current events ("is trending", "are discussing")
- Include relevant context without overwhelming the reader
- Make it feel timely and relevant to TODAY

Format the output as HTML. Use <h2> for main sections, <h3> for subsections, <p> for paragraphs, <ul>/<ol> for lists.
Do NOT include <html>, <head>, or <body> tags - just the article content.

Also provide:
- A compelling news headline (under 60 characters) that captures the trending aspect
- A meta description (under 160 characters) that explains why this is trending
- A CATEGORY from this exact list: AI, BIZ & IT, CARS, CULTURE, GAMING, HEALTH, POLICY, SCIENCE, SECURITY, SPACE, TECH
  Choose the single best-fitting category based on the article's primary subject matter.

Format your response as:
TITLE: [Your headline here]
META: [Your meta description here]
CATEGORY: [One category from the list above]
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
        meta_match = re.search(r'META:\s*(.+?)(?:\n|CATEGORY:|CONTENT:)', response_text, re.IGNORECASE)
        category_match = re.search(r'CATEGORY:\s*(.+?)(?:\n|CONTENT:)', response_text, re.IGNORECASE)
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

        # Extract and validate category
        category = 'TECH'  # default fallback
        if category_match:
            raw_category = category_match.group(1).strip().upper()
            if raw_category in VALID_CATEGORIES:
                category = raw_category
            else:
                logger.warning(f"Invalid category '{raw_category}', defaulting to TECH")
        else:
            logger.warning("No category found in response, defaulting to TECH")

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
            'topic': category,
            'trending_keyword': topic,
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

    # Get existing articles and trending keywords to avoid duplicates
    existing_titles = set()
    existing_keywords = set()
    try:
        from scripts.database import get_db_client, is_supabase_enabled
        if is_supabase_enabled():
            db = get_db_client()
            existing_articles = db.list_articles(limit=100, published_only=False)
            existing_titles = {a.get('title', '').lower() for a in existing_articles}
            logger.info(f"Loaded {len(existing_titles)} existing article titles for duplicate check")

            # Load existing trending keywords for keyword-to-keyword comparison
            db_keywords = db.list_trending_keywords(limit=200)
            existing_keywords = {k.lower() for k in db_keywords}
            logger.info(f"Loaded {len(existing_keywords)} existing trending keywords for duplicate check")
    except Exception as e:
        logger.warning(f"Could not load existing articles: {str(e)}")

    # Also load from local JSON index for fallback duplicate check
    try:
        import json
        from pathlib import Path
        index_path = Path(__file__).parent.parent.parent / 'frontend' / 'public' / 'articles' / 'index.json'
        if index_path.exists():
            with open(index_path, 'r') as f:
                local_articles = json.load(f)
            for a in local_articles:
                existing_titles.add(a.get('title', '').lower())
            logger.info(f"Loaded {len(local_articles)} local article titles for duplicate check")
    except Exception as e:
        logger.warning(f"Could not load local articles index: {str(e)}")

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

        # Skip if very similar topic exists (word overlap similarity)
        topic_lower = topic.lower()
        is_duplicate = False

        # 1. Compare new topic keyword against existing trending keywords (keyword-to-keyword)
        for existing_kw in existing_keywords:
            if _is_similar(topic_lower, existing_kw, threshold=0.4):
                logger.info(f"Skipping similar keyword (keyword match): '{topic}' ~ '{existing_kw}'")
                is_duplicate = True
                break

        # 2. Compare against existing article titles
        if not is_duplicate:
            for existing_title in existing_titles:
                if _is_similar(topic_lower, existing_title, threshold=0.35):
                    logger.info(f"Skipping similar topic (title match): '{topic}' ~ '{existing_title}'")
                    is_duplicate = True
                    break

        # 3. Also check against other topics in current batch
        if not is_duplicate:
            for used in used_topics:
                if _is_similar(topic_lower, used, threshold=0.4):
                    logger.info(f"Skipping similar topic in batch: '{topic}' ~ '{used}'")
                    is_duplicate = True
                    break

        if is_duplicate:
            continue

        logger.info(f"Generating article {len(articles)+1}/{articles_count}: {topic}")

        article = generate_article(topic, **kwargs)

        if article and article.get('word_count', 0) >= 500:
            # Post-generation semantic duplicate check using Claude Haiku
            if existing_titles and _is_semantic_duplicate(article['title'], existing_titles):
                logger.info(f"Skipping semantic duplicate: '{article['title']}'")
                continue

            # Add source information
            article['source_data'] = topic_data
            articles.append(article)
            used_topics.add(topic.lower())
            existing_titles.add(article['title'].lower())
        elif article:
            logger.warning(f"Article too short ({article.get('word_count', 0)} words), skipping: {topic}")
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
