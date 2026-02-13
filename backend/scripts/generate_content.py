"""
Content Generator using Gemini

Generates SEO-optimized blog articles using:
- Primary: Gemini 2.5 Pro via CLI (Google account auth, no API quota)
- Fallback: Gemini 3 Flash Preview via API (free tier)
"""

import logging
import os
import re
import subprocess
import shutil
import time
from typing import Dict, Optional
from datetime import datetime

try:
    import google.generativeai as genai
except ImportError:
    genai = None

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

# Gemini CLI path (cached)
_gemini_cli_path = shutil.which('gemini')


def _generate_with_gemini_cli(prompt: str, model: str = "gemini-2.5-pro") -> str:
    """Generate content using Gemini CLI (uses Google account auth, no API quota)."""
    if not _gemini_cli_path:
        raise RuntimeError("Gemini CLI not installed")

    logger.info(f"Calling Gemini CLI ({model})...")
    result = subprocess.run(
        [_gemini_cli_path, '-m', model, '-p', prompt],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Gemini CLI error: {result.stderr.strip()}")

    # Filter out CLI status lines
    lines = result.stdout.strip().split('\n')
    content_lines = [l for l in lines
                     if not l.startswith('Loaded cached')
                     and not l.startswith('Hook registry')]
    return '\n'.join(content_lines)


def _generate_with_gemini_api(prompt: str, model_name: str = "gemini-3-flash-preview") -> str:
    """Generate content using Google Gemini API (free tier)."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    logger.info(f"Calling Gemini API ({model_name})...")
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=4096,
        )
    )
    return response.text


def _is_similar(text_a: str, text_b: str, threshold: float = 0.35) -> bool:
    """Check if two texts are similar using word overlap (Jaccard similarity)."""
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

    if words_a.issubset(words_b) or words_b.issubset(words_a):
        return True

    return similarity >= threshold


def _is_semantic_duplicate(new_title: str, existing_titles: set) -> bool:
    """Use LLM to check if a generated article title covers the same topic as any existing article."""
    try:
        titles_list = '\n'.join(list(existing_titles)[:50])
        prompt = (
            f'Does this new article title cover the SAME topic as any existing article?\n\n'
            f'New title: {new_title}\n\n'
            f'Existing titles:\n{titles_list}\n\n'
            f'Reply ONLY "YES" or "NO".'
        )

        # Try Gemini API first (fast, lightweight task)
        try:
            resp_text = _generate_with_gemini_api(prompt)
            answer = resp_text.strip().upper()
            time.sleep(3)
            if answer == 'YES':
                logger.info(f"Semantic duplicate detected (Gemini API): '{new_title}'")
                return True
            return False
        except Exception as e:
            logger.warning(f"Gemini API dedup check failed: {e}")

        # Fallback to Gemini CLI
        try:
            resp_text = _generate_with_gemini_cli(prompt, model="gemini-2.5-flash")
            answer = resp_text.strip().upper()
            if answer == 'YES':
                logger.info(f"Semantic duplicate detected (Gemini CLI): '{new_title}'")
                return True
            return False
        except Exception as e:
            logger.warning(f"Gemini CLI dedup check failed: {e}")

        return False
    except Exception as e:
        logger.warning(f"Semantic duplicate check failed: {e}")
        return False


def calculate_reading_time(text: str, words_per_minute: int = 200) -> int:
    """Calculate estimated reading time for text."""
    clean_text = re.sub(r'<[^>]+>', '', text)
    word_count = len(clean_text.split())
    reading_time = max(1, round(word_count / words_per_minute))
    return reading_time


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """Extract potential keywords from content."""
    clean_text = re.sub(r'<[^>]+>', '', content)
    words = re.findall(r'\b[a-z]{4,}\b', clean_text.lower())

    word_freq = {}
    for word in words:
        word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]

    return keywords


VALID_CATEGORIES = [
    'AI', 'BIZ & IT', 'CARS', 'CULTURE', 'GAMING', 'HEALTH',
    'POLICY', 'SCIENCE', 'SECURITY', 'SPACE', 'TECH',
]


def _build_prompt(topic: str, min_words: int, max_words: int, target_audience: str) -> str:
    """Build the article generation prompt."""
    return f"""Write a comprehensive, trending news article analyzing: {topic}

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


def _parse_response(response_text: str, topic: str) -> Dict:
    """Parse LLM response into article dictionary."""
    title_match = re.search(r'TITLE:\s*(.+?)(?:\n|META:)', response_text, re.IGNORECASE)
    meta_match = re.search(r'META:\s*(.+?)(?:\n|CATEGORY:|CONTENT:)', response_text, re.IGNORECASE)
    category_match = re.search(r'CATEGORY:\s*(.+?)(?:\n|CONTENT:)', response_text, re.IGNORECASE)
    content_match = re.search(r'CONTENT:\s*(.+)', response_text, re.IGNORECASE | re.DOTALL)

    if not all([title_match, meta_match, content_match]):
        logger.error("Failed to parse response properly")
        title = topic
        meta_description = f"Learn about {topic}"
        content = response_text
    else:
        title = title_match.group(1).strip()
        meta_description = meta_match.group(1).strip()
        content = content_match.group(1).strip()

    category = 'TECH'
    if category_match:
        raw_category = category_match.group(1).strip().upper()
        if raw_category in VALID_CATEGORIES:
            category = raw_category
        else:
            logger.warning(f"Invalid category '{raw_category}', defaulting to TECH")

    word_count = len(re.sub(r'<[^>]+>', '', content).split())
    reading_time = calculate_reading_time(content)
    keywords = extract_keywords(content)

    return {
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


def generate_article(
    topic: str,
    min_words: int = 1500,
    max_words: int = 2000,
    target_audience: str = "North American and European readers",
    **kwargs,
) -> Dict:
    """
    Generate a complete SEO-optimized article.
    Primary: Gemini 2.5 Pro via CLI
    Fallback: Gemini API (gemini-3-flash-preview)
    """
    logger.info(f"Generating article about: {topic}")
    logger.info(f"Target length: {min_words}-{max_words} words")

    prompt = _build_prompt(topic, min_words, max_words, target_audience)

    # Primary: Gemini CLI (gemini-2.5-pro, Google account auth)
    if _gemini_cli_path:
        try:
            response_text = _generate_with_gemini_cli(prompt)
            article = _parse_response(response_text, topic)
            logger.info(f"[Gemini CLI] Article generated: {article['title']} ({article['word_count']} words)")
            article['_provider'] = 'gemini-cli'
            return article
        except Exception as e:
            logger.warning(f"Gemini CLI failed: {e}")

    # Fallback: Gemini API (gemini-3-flash-preview)
    if os.getenv('GOOGLE_API_KEY') and genai:
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 30 * attempt
                    logger.info(f"Rate limit retry {attempt}/3, waiting {wait}s...")
                    time.sleep(wait)
                response_text = _generate_with_gemini_api(prompt)
                article = _parse_response(response_text, topic)
                logger.info(f"[Gemini API] Article generated: {article['title']} ({article['word_count']} words)")
                article['_provider'] = 'gemini-api'
                time.sleep(5)
                return article
            except Exception as e:
                if '429' in str(e) or 'quota' in str(e).lower() or 'rate' in str(e).lower():
                    logger.warning(f"Gemini API rate limit hit (attempt {attempt+1}/3)")
                    continue
                logger.error(f"Gemini API error: {e}")
                return {}
        logger.error("Gemini API rate limit exhausted after 3 retries")

    logger.error("No LLM provider available (Gemini CLI and Gemini API both failed).")
    return {}


def generate_multiple_articles(
    topics: list,
    articles_count: int = 3,
    **kwargs
) -> list:
    """Generate multiple articles from a list of topics with duplicate checking."""
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

        # 1. Compare new topic keyword against existing trending keywords
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
            # Post-generation semantic duplicate check
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
    print("Testing content generation...\n")

    test_topic = "Artificial Intelligence in Healthcare"

    print(f"Generating article about: {test_topic}")
    article = generate_article(
        topic=test_topic,
        min_words=500,
        max_words=800
    )

    if article:
        print("\n=== Generated Article ===")
        print(f"Provider: {article.get('_provider', 'unknown')}")
        print(f"Title: {article['title']}")
        print(f"Meta: {article['meta_description']}")
        print(f"Word Count: {article['word_count']}")
        print(f"Reading Time: {article['reading_time']} minutes")
        print(f"Keywords: {', '.join(article['keywords'][:5])}")
        print(f"\nContent Preview (first 200 chars):")
        print(article['content'][:200] + "...")
    else:
        print("Failed to generate article")
