"""
Content Generator using Gemini

Generates SEO-optimized blog articles using:
- Primary: Gemini 2.5 Pro via CLI (Google account auth, no API quota)
- Fallback: Gemini 3 Flash Preview via API (free tier)
"""

import logging
import os
import random
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


STOP_WORDS = {
    'this', 'that', 'with', 'from', 'which', 'their', 'there', 'these',
    'those', 'then', 'than', 'them', 'they', 'been', 'being', 'were',
    'have', 'having', 'does', 'doing', 'done', 'will', 'would', 'could',
    'should', 'might', 'must', 'shall', 'about', 'above', 'after', 'again',
    'also', 'another', 'back', 'because', 'before', 'between', 'both',
    'came', 'come', 'each', 'even', 'every', 'find', 'first', 'found',
    'give', 'going', 'gone', 'good', 'great', 'help', 'here', 'high',
    'however', 'into', 'just', 'keep', 'know', 'known', 'last', 'left',
    'like', 'line', 'long', 'look', 'made', 'make', 'many', 'more',
    'most', 'much', 'need', 'never', 'next', 'only', 'open', 'other',
    'over', 'part', 'point', 'really', 'right', 'same', 'seem', 'show',
    'side', 'since', 'small', 'some', 'something', 'still', 'such',
    'sure', 'take', 'tell', 'thing', 'think', 'through', 'time', 'turn',
    'under', 'upon', 'used', 'using', 'very', 'want', 'well', 'what',
    'when', 'where', 'while', 'work', 'world', 'year', 'your',
    'able', 'allow', 'around', 'away', 'become', 'best', 'better',
    'call', 'case', 'change', 'clear', 'close', 'consider', 'create',
    'current', 'different', 'down', 'early', 'else', 'enough', 'ever',
    'example', 'face', 'fact', 'feel', 'form', 'full', 'further',
    'general', 'gets', 'given', 'goes', 'hand', 'hard', 'head',
    'home', 'house', 'human', 'important', 'include', 'issue', 'itself',
    'kind', 'large', 'late', 'lead', 'least', 'less', 'level', 'life',
    'likely', 'live', 'local', 'makes', 'matter', 'mean', 'means',
    'move', 'name', 'near', 'number', 'offer', 'often', 'order',
    'place', 'plan', 'play', 'possible', 'power', 'problem', 'provide',
    'public', 'question', 'quite', 'read', 'real', 'reason', 'result',
    'room', 'said', 'says', 'second', 'sense', 'service', 'several',
    'simply', 'sort', 'start', 'state', 'story', 'system', 'term',
    'things', 'thought', 'today', 'together', 'took', 'true', 'until',
    'ways', 'whole', 'word', 'words', 'wrote', 'years',
    'also', 'already', 'always', 'among', 'based', 'bring', 'built',
    'called', 'comes', 'common', 'complete', 'control', 'design',
    'developed', 'doesn', 'during', 'either', 'enable', 'entire',
    'exactly', 'feature', 'features', 'following', 'ground', 'group',
    'growing', 'itself', 'major', 'making', 'model', 'models',
    'modern', 'natural', 'needs', 'original', 'particularly',
    'people', 'potential', 'rather', 'remain', 'running', 'single',
    'specific', 'support', 'taken', 'three', 'toward', 'towards',
    'type', 'types', 'understanding', 'without',
    'adsbygoogle', 'window', 'push', 'pagead', 'script', 'class',
    'style', 'href', 'http', 'https', 'data', 'content', 'users',
}


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """Extract meaningful keywords from content, filtering stop words."""
    clean_text = re.sub(r'<[^>]+>', '', content)
    words = re.findall(r'\b[a-z]{4,}\b', clean_text.lower())

    word_freq = {}
    for word in words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 1

    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]

    return keywords


VALID_CATEGORIES = [
    'IT & BIZ', 'CULTURE', 'ECONOMY', 'ENTERTAINMENT',
    'GAMING', 'HEALTH', 'POLICY', 'SCIENCE', 'SECURITY', 'TECH',
]

# Author personas — gender + age + writing voice
AUTHOR_PERSONAS = {
    'Alex Chen': {
        'gender': 'male',
        'voice': (
            "You are Alex Chen, a 35-year-old senior tech editor. "
            "You've spent a decade covering Silicon Valley and have strong opinions shaped by "
            "years of watching hype cycles come and go. Your writing voice is direct and confident — "
            "you don't hedge with 'perhaps' or 'maybe'. You use dry humor and occasionally reference "
            "your own experience debugging code at 2am or sitting through countless product launches. "
            "You write like a guy who's seen enough tech trends to be skeptical but still genuinely excited "
            "when something real breaks through. Think: a smart friend who works in tech explaining things over beer."
        ),
    },
    'Sarah Mitchell': {
        'gender': 'female',
        'voice': (
            "You are Sarah Mitchell, a 38-year-old business and policy correspondent. "
            "You came up through financial journalism and have a sharp eye for the money trail behind every story. "
            "Your writing is precise and incisive — you cut through PR spin and find the real numbers. "
            "You occasionally share brief personal observations from covering policy summits or interviewing executives. "
            "You write with the authority of someone who's read every quarterly report and isn't impressed by buzzwords. "
            "Think: a sharp colleague who always knows what the real story is behind the press release."
        ),
    },
    'Maya Rodriguez': {
        'gender': 'female',
        'voice': (
            "You are Maya Rodriguez, a 32-year-old culture and entertainment editor. "
            "You grew up as a gamer and internet native, and your writing reflects genuine passion for the communities you cover. "
            "Your voice is warm, witty, and culturally fluent — you make references that your audience actually gets. "
            "You're not afraid to express genuine enthusiasm or disappointment. You write like someone who's actually "
            "part of these communities, not an outsider looking in. "
            "Think: your most culturally plugged-in friend who also happens to write really well."
        ),
    },
}
DEFAULT_PERSONA = AUTHOR_PERSONAS['Alex Chen']


def _get_author_for_category(category: str) -> str:
    """Return author name for a given category."""
    cat_author = {
        'IT & BIZ': 'Alex Chen', 'TECH': 'Alex Chen',
        'SECURITY': 'Alex Chen', 'SCIENCE': 'Alex Chen',
        'POLICY': 'Sarah Mitchell', 'ECONOMY': 'Sarah Mitchell',
        'HEALTH': 'Sarah Mitchell',
        'CULTURE': 'Maya Rodriguez', 'GAMING': 'Maya Rodriguez',
        'ENTERTAINMENT': 'Maya Rodriguez',
    }
    return cat_author.get((category or '').upper(), 'Alex Chen')


def _build_prompt(
    topic: str,
    min_words: int,
    max_words: int,
    target_audience: str,
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
) -> str:
    """Build the article generation prompt."""

    # Build internal links section (minimal - only when highly relevant)
    internal_links_section = ""
    if existing_articles:
        links_list = "\n".join(
            f"- \"{a['title']}\" -> /article/{a['slug']}"
            for a in existing_articles[:30]
        )
        internal_links_section = f"""
INTERNAL LINKING (LOW PRIORITY - use sparingly):
Below are existing articles on our site. Only link to one if it is DIRECTLY and strongly related to the current topic.
Use 0-1 internal links at most. Prefer external links over internal links.
Use HTML anchor tags like: <a href="/article/SLUG">Article Title</a>

Existing articles:
{links_list}
"""

    # Build source reference section
    source_section = ""
    if source_url:
        source_section = f"""
SOURCE REFERENCE:
The original source for this trending topic is: {source_url}
You may reference or link to this source in the article where appropriate using <a href="{source_url}" target="_blank" rel="noopener noreferrer">source text</a>.
"""

    # External links section
    external_links_section = """
EXTERNAL LINKING (HIGH PRIORITY - credibility & SEO):
You MUST naturally embed 4-6 outbound links to reputable external sources within the article body. External links are the PRIMARY link type for this article.
Use HTML anchor tags: <a href="URL" target="_blank" rel="noopener noreferrer">descriptive text</a>
Link to well-known, authoritative sites such as:
- Wikipedia (for background context, definitions, historical references)
- Official company/organization websites (e.g., apple.com, nasa.gov, who.int)
- Major news outlets (e.g., Reuters, AP News, BBC, The Verge, TechCrunch, Ars Technica, Wired)
- Government or institutional sources (e.g., FDA, SEC, EPA, NIH, EU official sites)
- Academic or research sources when relevant
Rules:
- Links must be REAL, well-known URLs that are very likely to exist (e.g., https://en.wikipedia.org/wiki/Topic_Name, https://www.reuters.com/, https://techcrunch.com/)
- Do NOT fabricate specific article URLs - link to homepage or Wikipedia topic pages instead
- Weave links naturally into sentences, do NOT create a separate "References" or "Sources" section
- Example: "According to <a href="https://en.wikipedia.org/wiki/Artificial_intelligence" target="_blank" rel="noopener noreferrer">Wikipedia</a>, artificial intelligence has evolved rapidly since..."
- Example: "The announcement was first reported by <a href="https://www.reuters.com/" target="_blank" rel="noopener noreferrer">Reuters</a>, indicating..."
"""

    # Author persona
    persona = AUTHOR_PERSONAS.get(author_name, DEFAULT_PERSONA)
    persona_voice = persona['voice']

    return f"""Write an in-depth analytical article about this trending topic: {topic}

AUTHOR IDENTITY (THIS IS WHO YOU ARE — stay in character throughout):
{persona_voice}

You are writing for a tech-savvy audience aged 25-45. This is NOT a generic news summary — it is an ORIGINAL ANALYSIS piece with YOUR personal perspective. Readers come to NexusTopic specifically for the human editorial voice, not wire-service regurgitation.

CRITICAL WRITING RULES (anti-AI detection):
- NEVER start with "In a move that..." / "In an era where..." / "The tech world is buzzing..."
- NEVER use: "It remains to be seen", "Only time will tell", "In conclusion", "It's worth noting", "landscape", "paradigm shift", "game-changer", "dive into", "delve into", "tapestry", "multifaceted"
- VARY sentence length dramatically: mix punchy (5-8 words) with longer analytical ones
- Use FIRST PERSON naturally as your character would: share brief personal reactions, professional experiences, or opinions
- Include at least ONE contrarian or unexpected angle
- Add SPECIFIC numbers, dates, percentages, or dollar amounts wherever possible
- Use rhetorical questions naturally: "But here's the real question:" or "So why does this matter?"
- Write imperfect, human sentences — occasional fragments, em dashes, parenthetical asides are GOOD
- Avoid perfectly parallel sentence structures that scream "AI generated"

Article Requirements:
- Target audience: {target_audience}
- Word count: {min_words}-{max_words} words
- Format: HTML with semantic tags (h2, h3, p, ul, ol, strong, em, blockquote)
- Tone: Smart, opinionated, conversational — like a knowledgeable colleague explaining over coffee
- SEO: Include relevant keywords naturally
{internal_links_section}{external_links_section}{source_section}
The article MUST include these elements (but DO NOT use these exact headings — create original, engaging section titles):

1. **A hook that makes readers stop scrolling** — Start with the most surprising or consequential detail, not a summary
2. **The "So What?" context** — Why should a busy reader care about this RIGHT NOW? What changes for them?
3. **Data & evidence** — Include at least 2-3 specific statistics, market figures, user numbers, or research findings. Use <strong> tags to highlight key numbers
4. **An angle others are missing** — What are mainstream outlets NOT saying? What's the deeper pattern or second-order effect?
5. **Comparison with precedent** — Compare this to a previous similar event or the existing approach. Example: "Compared to method A, this new approach B is innovative because..." or "The last time something like this happened was in 2021, and here's what followed."
6. **Your editorial take** — A clearly labeled opinion section (use <blockquote> for editorial commentary). What do YOU think this means?
7. **Future impact projection** — THIS IS CRITICAL. Do NOT end with vague platitudes. Instead, make a SPECIFIC prediction:
   - "If this technology reaches commercial scale, expect [specific change] in [specific industry] within [timeframe]"
   - "For professionals in [specific field], this signals that [specific actionable insight]"
   - "The downstream effect I'm watching: [specific second-order consequence that isn't obvious]"
   This is the section that separates human insight from AI regurgitation. Be bold. Be specific. Be willing to be wrong.

STYLE GUIDE:
- Write like a columnist, not a wire service — personality and perspective matter
- Break up walls of text with short paragraphs (2-3 sentences max)
- Use <blockquote> for editorial asides: "Editor's take: This is bigger than it looks because..."
- Embed data naturally: "That 47% year-over-year jump isn't just impressive — it's unprecedented in this sector"
- Use analogies and comparisons to make complex topics accessible
- End with your specific prediction, not a vague "time will tell" cop-out

Format: HTML only (h2, h3, p, ul, ol, strong, em, blockquote). No <html>/<head>/<body> tags.

Also provide:
- A HEADLINE (under 60 chars) that DEMANDS attention. This is the MOST IMPORTANT part for search CTR.
  HEADLINE RULES:
  * Use numbers when possible: "5 Reasons...", "The $2B Problem...", "3 Things..."
  * Use power words: "Shocking", "Critical", "Secret", "Urgent", "Revealed", "Devastating"
  * Use curiosity gaps: "Why X Is Actually Y", "The Real Reason Behind X", "What Nobody Tells You About X"
  * Use question format when natural: "Is X the End of Y?", "Why Can't X Do Y?"
  * Include specific details: names, numbers, dates — NOT vague generic titles
  * NEVER use generic titles like "The Future of AI" or "Understanding Blockchain"
  * Think: would YOU stop scrolling to click this? If not, rewrite it.
  * Examples of GREAT titles: "Tesla's $500M Gamble Just Backfired", "Why Google Killed Its Own AI Project", "The 3 Lines of Code That Crashed AWS"
  * Examples of BAD titles: "Exploring the Impact of Technology", "AI Continues to Evolve", "New Developments in Tech"

- A META DESCRIPTION (under 155 chars) optimized for search CTR:
  * Start with a hook — the most surprising fact or consequence
  * Include a number or specific detail
  * End with an implied benefit of reading: what will the reader learn or understand?
  * Use active voice and urgency
  * Example: "A single API change broke 40% of plugins overnight. Here's what went wrong and what developers need to do now."

- A CATEGORY from: IT & BIZ, CULTURE, ECONOMY, ENTERTAINMENT, GAMING, HEALTH, POLICY, SCIENCE, SECURITY, TECH

Format your response as:
TITLE: [headline]
META: [meta description]
CATEGORY: [category]
CONTENT:
[HTML content]
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
    min_words: int = 500,
    max_words: int = 700,
    target_audience: str = "North American and European readers",
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
    **kwargs,
) -> Dict:
    """
    Generate a complete SEO-optimized article.
    Primary: Gemini 2.5 Pro via CLI
    Fallback: Gemini API (gemini-3-flash-preview)
    """
    # Randomize word count target within the given range for natural variation
    target = random.randint(min_words, max_words)
    # Set effective min to ~70% of target, effective max to target
    effective_min = max(min_words, int(target * 0.7))
    effective_max = target

    logger.info(f"Generating article about: {topic}")
    logger.info(f"Target length: {effective_min}-{effective_max} words (from range {min_words}-{max_words})")

    prompt = _build_prompt(
        topic, effective_min, effective_max, target_audience,
        existing_articles=existing_articles,
        source_url=source_url,
        author_name=author_name,
    )

    def _try_generate(provider_name, generate_fn, max_retries=2):
        """Try generating and retry once if word count is too low."""
        for retry in range(max_retries):
            response_text = generate_fn()
            article = _parse_response(response_text, topic)
            wc = article.get('word_count', 0)
            if wc >= effective_min:
                logger.info(f"[{provider_name}] Article generated: {article['title']} ({wc} words)")
                return article
            if retry < max_retries - 1:
                logger.warning(f"[{provider_name}] Article too short ({wc}/{effective_min} words), retrying...")
                time.sleep(3)
            else:
                logger.warning(f"[{provider_name}] Article still short ({wc}/{effective_min} words), accepting anyway")
                return article
        return None

    # Primary: Gemini CLI (gemini-2.5-pro, Google account auth)
    if _gemini_cli_path:
        try:
            article = _try_generate('Gemini CLI', lambda: _generate_with_gemini_cli(prompt))
            if article:
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
                article = _try_generate('Gemini API', lambda: _generate_with_gemini_api(prompt))
                if article:
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
    existing_articles_for_links = []  # For internal linking in prompts
    try:
        from scripts.database import get_db_client, is_supabase_enabled
        if is_supabase_enabled():
            db = get_db_client()
            existing_articles = db.list_articles(limit=100, published_only=False)
            existing_articles_for_links = [
                {'title': a.get('title', ''), 'slug': a.get('slug', '')}
                for a in existing_articles if a.get('slug')
            ]
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

        quick_cat = topic_data.get('_quick_cat', '?')
        author_name = _get_author_for_category(quick_cat)
        logger.info(f"Generating article {len(articles)+1}/{articles_count} [{quick_cat}] by {author_name}: {topic}")

        source_url = topic_data.get('url', '')
        article = generate_article(
            topic,
            existing_articles=existing_articles_for_links,
            source_url=source_url,
            author_name=author_name,
            **kwargs,
        )

        if article and article.get('word_count', 0) >= 300:
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
