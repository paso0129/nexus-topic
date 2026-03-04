"""
Content Generator using Gemini

Generates SEO-optimized blog articles using:
- Primary: Gemini 3.1 Pro Preview via CLI (Google account auth, no API quota)
- Fallback: Gemini 2.5 Pro via API (free tier)
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
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

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


def _generate_with_gemini_cli(prompt: str, model: str = "gemini-3.1-pro-preview") -> str:
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


def _get_genai_client():
    """Get or create a Gemini API client."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key or not genai:
        raise RuntimeError("Gemini API not available")
    return genai.Client(api_key=api_key)


def _generate_with_gemini_api(prompt: str, model_name: str = "gemini-2.5-pro") -> str:
    """Generate content using Google Gemini API (free tier)."""
    client = _get_genai_client()
    logger.info(f"Calling Gemini API ({model_name})...")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=4096,
        ),
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
    """Use LLM to check if a generated article title covers the EXACT same specific story as any existing article."""
    try:
        titles_list = '\n'.join(list(existing_titles)[:50])
        prompt = (
            f'Does this new article title cover the EXACT SAME specific story, event, or announcement as any existing article?\n\n'
            f'IMPORTANT: Two articles about the same broad category (e.g., both about "stock market" or "cryptocurrency") '
            f'are NOT duplicates. They must be about the SAME specific event, company announcement, or news story.\n\n'
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


def _validate_internal_links(content: str, valid_slugs: set) -> str:
    """Remove internal links whose slugs don't exist in the database."""
    def replace_link(match):
        slug = match.group(1)
        anchor_text = match.group(2)
        if slug in valid_slugs:
            return match.group(0)  # keep valid link
        logger.warning(f"Removing invalid internal link: /article/{slug}")
        return anchor_text  # replace with just the anchor text

    return re.sub(
        r'<a\s+href="/article/([^"]+)"[^>]*>(.*?)</a>',
        replace_link,
        content,
    )


def extract_keywords(content: str, max_keywords: int = 10) -> list:
    """Extract meaningful keywords from content, with 3x weight for H2/H3 headings."""
    # Extract heading text with 3x weight
    heading_texts = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', content, re.IGNORECASE)
    heading_clean = ' '.join(re.sub(r'<[^>]+>', '', h) for h in heading_texts)
    heading_words = re.findall(r'\b[a-z]{4,}\b', heading_clean.lower())

    # Extract body text
    clean_text = re.sub(r'<[^>]+>', '', content)
    body_words = re.findall(r'\b[a-z]{4,}\b', clean_text.lower())

    word_freq = {}
    for word in body_words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 1
    # Apply 3x weight for heading words
    for word in heading_words:
        if word not in STOP_WORDS:
            word_freq[word] = word_freq.get(word, 0) + 3

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
    'Daniel Park': {
        'gender': 'male',
        'voice': (
            "You are Daniel Park, a 40-year-old economy and markets editor. "
            "You spent 8 years as a Wall Street analyst before switching to journalism, "
            "and you still think in numbers before narratives. Your writing turns complex "
            "market moves, trade wars, and macro trends into stories anyone can follow. "
            "You're blunt about when the market is irrational and not afraid to call out "
            "corporate spin. You drop real data points — not vague percentages — and you "
            "connect the dots between policy decisions and your reader's wallet. "
            "Think: the friend who actually understands what the Fed just did and explains it without jargon."
        ),
    },
}
DEFAULT_PERSONA = AUTHOR_PERSONAS['Alex Chen']


def _get_author_for_category(category: str) -> str:
    """Return author name for a given category."""
    cat_author = {
        'IT & BIZ': 'Alex Chen', 'TECH': 'Alex Chen',
        'SECURITY': 'Alex Chen', 'SCIENCE': 'Alex Chen',
        'POLICY': 'Sarah Mitchell', 'HEALTH': 'Sarah Mitchell',
        'ECONOMY': 'Daniel Park',
        'CULTURE': 'Maya Rodriguez', 'GAMING': 'Maya Rodriguez',
        'ENTERTAINMENT': 'Maya Rodriguez',
    }
    return cat_author.get((category or '').upper(), 'Alex Chen')


ARTICLE_STRUCTURES = [
    # Structure A: Investigative — "follow the money" / "what they're not telling you"
    """The article should follow an INVESTIGATIVE structure:
1. **Lead with the buried headline** — What's the most consequential detail that other outlets buried in paragraph 6? Start there.
2. **The official narrative vs reality** — Present what companies/officials are saying, then dismantle it with data
3. **Follow the money** — Who benefits financially? Show specific dollar amounts, market caps, revenue figures
4. **The historical parallel** — Find a previous event with a similar pattern. What happened then? What does it predict now?
5. **The stakeholders nobody's talking about** — Who else is affected that mainstream coverage ignores?
6. **Your verdict** — State your position clearly, backed by the evidence you've presented. No hedging.
7. **The one metric to watch** — Give readers a single, specific indicator they can track to see if your analysis is correct""",

    # Structure B: Explainer — "here's what you need to know"
    """The article should follow an EXPLAINER structure:
1. **The 30-second version** — Open with a punchy 2-3 sentence summary that a busy reader can screenshot and share
2. **Why this matters to YOU** — Make it personal. How does this affect the reader's job, wallet, or daily life?
3. **How we got here** — A brief, sharp timeline (use a numbered/bulleted list) of the 3-5 key events leading to this moment
4. **How it actually works** — Break down the technical/complex parts with analogies. Compare to something the reader already understands
5. **The debate** — Present the strongest argument FOR and AGAINST. Use real quotes or positions from named figures
6. **What happens next** — Lay out 2-3 specific scenarios with probabilities. "Most likely (60%): ... Less likely but possible (30%): ..."
7. **The bottom line** — One paragraph, one clear takeaway the reader should remember""",

    # Structure C: Contrarian — challenge the consensus
    """The article should follow a CONTRARIAN structure:
1. **State the consensus** — What does everyone assume about this topic? Lay it out fairly in 2-3 sentences
2. **The crack in the narrative** — Identify the one data point, trend, or overlooked fact that undermines the consensus
3. **Build the counter-case** — Present your alternative interpretation with 3+ supporting data points. Use <strong> for key numbers
4. **The strongest objection** — What's the best argument against YOUR position? Address it honestly — don't strawman
5. **The real-world test** — How would we know if you're right or wrong? Name specific, measurable outcomes within a timeframe
6. **Who's already betting on this** — Name companies, investors, or researchers who are quietly acting on this contrarian view
7. **Your call to action** — Tell the reader what to do differently based on this analysis""",

    # Structure D: Deep-dive profile — focus on a person, company, or technology
    """The article should follow a DEEP-DIVE structure:
1. **The defining moment** — Open with a specific scene, quote, or event that captures the essence of the story
2. **The backstory** — How did we get to this point? Focus on the 2-3 decisions or events that matter most
3. **By the numbers** — A data-rich section with at least 4-5 specific statistics. Present them visually with bullet points or comparisons
4. **The competitive landscape** — Who are the key players? Use a brief comparison (Company A does X, Company B does Y, our subject does Z)
5. **The hidden risk** — What could go wrong that nobody is pricing in? Be specific about the vulnerability
6. **The insider perspective** — Share insight that feels like it comes from someone who actually works in this space
7. **The 12-month outlook** — Where will this story be in a year? Make a specific, falsifiable prediction""",
]


def _build_prompt(
    topic: str,
    min_words: int,
    max_words: int,
    target_audience: str,
    existing_articles: list = None,
    source_url: str = None,
    author_name: str = None,
    search_context: dict = None,
) -> str:
    """Build the article generation prompt."""
    # Randomly select article structure for variety
    structure_block = random.choice(ARTICLE_STRUCTURES)

    # Build internal links section
    internal_links_section = ""
    if existing_articles:
        links_list = "\n".join(
            f"- \"{a['title']}\" [{a.get('topic', '')}] -> /article/{a['slug']}"
            for a in existing_articles[:30]
        )
        internal_links_section = f"""
INTERNAL LINKING (IMPORTANT for SEO):
Below are existing articles on our site with their categories. Link to 2-3 articles that are RELATED to the current topic.
Use HTML anchor tags: <a href="/article/SLUG">descriptive anchor text</a>
Rules:
- Choose articles from the same or related categories when possible
- Use descriptive anchor text (not "click here" or the full title) — use natural phrases
- Spread links throughout the article body, not clustered together
- ONLY use slugs from the list below — do NOT invent slugs

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

    # Build real search data section
    search_data_section = ""
    if search_context:
        parts = []
        ac = search_context.get('autocomplete', [])
        if ac:
            ac_lines = "\n".join(f'  - "{q}"' for q in ac[:15])
            parts.append(f"Google Autocomplete suggestions (what people actually search):\n{ac_lines}")
        top = search_context.get('related_top', [])
        if top:
            top_lines = "\n".join(f'  - "{q}"' for q in top[:10])
            parts.append(f"Top related search queries (from Google Trends):\n{top_lines}")
        rising = search_context.get('related_rising', [])
        if rising:
            rising_lines = "\n".join(f'  - "{q}"' for q in rising[:10])
            parts.append(f"Rising search queries (fast-growing interest):\n{rising_lines}")
        if parts:
            search_data_section = f"""
REAL SEARCH DATA (use this to optimize for actual search behavior):
{chr(10).join(parts)}

How to use this data:
- Use at least 2 of these real queries as H2 headings (rephrased naturally)
- Use 3-5 of these as FAQ questions
- Weave relevant keywords naturally into content
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
{internal_links_section}{external_links_section}{source_section}{search_data_section}
HEADING OPTIMIZATION (critical for search visibility):
- MANDATORY: At least 2 of your H2 headings MUST be in question form (ending with ?). This is a HARD REQUIREMENT — articles without 2+ question H2s will be rejected.
  * If REAL SEARCH DATA is provided above, turn those actual queries into H2 question headings
  * Use formats like: "What Is [Topic] and Why Does It Matter?", "How Does [Technology] Work?", "Is [X] Worth It in 2026?"
  * These question headings help the article appear in Google's "People Also Ask" boxes
- Other H2/H3 headings should contain relevant keywords naturally

{structure_block}

STYLE GUIDE:
- Write like a columnist, not a wire service — personality and perspective matter
- Break up walls of text with short paragraphs (2-3 sentences max)
- Embed data naturally: "That 47% year-over-year jump isn't just impressive — it's unprecedented in this sector"
- Use analogies and comparisons to make complex topics accessible
- End with a strong, specific conclusion — never vague "time will tell" cop-outs
- IMPORTANT: Do NOT use "Editor's Take:" labels or "My Prediction:" labels — weave opinions and forecasts naturally into the prose like a real columnist would

FAQ SECTION (append AFTER the main article body — does NOT count toward the word count):
After the main article content, add exactly this structure:
<h2>Frequently Asked Questions</h2>
Then 3-5 Q&A pairs, each as:
<h3>[Question in natural search query form, ending with ?]</h3>
<p>[Concise, specific answer with facts/numbers — 2-3 sentences max]</p>
Rules for FAQ:
- Questions must reflect what real users would type into Google about this topic
- Answers must contain specific facts, not vague generalities
- Do NOT repeat information already covered in the main article — add NEW useful details
- Example question formats: "How much does X cost?", "Is X better than Y?", "When will X be available?"

Format: HTML only (h2, h3, p, ul, ol, strong, em, blockquote). No <html>/<head>/<body> tags.

Also provide:
- A HEADLINE (under 60 chars) optimized for BOTH search ranking AND click-through.
  HEADLINE RULES:
  * Place the primary topic keyword in the FIRST 3-4 words of the headline
  * Use at most ONE power word (e.g., "Critical", "Revealed") — avoid stacking multiple
  * Use question format when it matches search intent: "Why Does X Matter?", "How Does X Work?"
  * Include specific details: names, numbers, dates — NOT vague generic titles
  * NEVER use generic titles like "The Future of AI" or "Understanding Blockchain"
  * The headline should clearly signal what the reader will learn, not just tease
  * Examples of GREAT titles: "Tesla Battery Costs Drop 40% in 2025", "Why Google Killed Its Own AI Project", "GPT-5 vs Gemini 3: Key Differences Explained"
  * Examples of BAD titles: "Exploring the Impact of Technology", "Shocking AI Revelation Changes Everything", "You Won't Believe What Happened"

- A META DESCRIPTION (STRICTLY under 155 characters — count carefully, this is a HARD LIMIT):
  * Start by answering the most likely search query about this topic in one sentence
  * Include 2-3 relevant keywords naturally (not stuffed)
  * Use active voice, be specific with numbers/facts
  * MUST be under 155 characters total including spaces and punctuation
  * Example (142 chars): "Tesla's new battery cuts EV costs by 40%. Here's how the 4680 cell changes pricing, range, and what it means for buyers."

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
    search_context: dict = None,
    **kwargs,
) -> Dict:
    """
    Generate a complete SEO-optimized article.
    Primary: Gemini 3.1 Pro Preview via CLI
    Fallback: Gemini API (gemini-2.5-pro)
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
        search_context=search_context,
    )

    # Collect valid slugs for internal link validation
    valid_slugs = set()
    if existing_articles:
        valid_slugs = {a['slug'] for a in existing_articles if a.get('slug')}

    def _try_generate(provider_name, generate_fn, max_retries=2):
        """Try generating and retry once if word count is too low."""
        for retry in range(max_retries):
            response_text = generate_fn()
            article = _parse_response(response_text, topic)
            # Validate internal links
            if valid_slugs and article.get('content'):
                article['content'] = _validate_internal_links(article['content'], valid_slugs)
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

    # Primary: Gemini CLI (gemini-3.1-pro-preview, Google account auth)
    if _gemini_cli_path:
        try:
            article = _try_generate('Gemini CLI', lambda: _generate_with_gemini_cli(prompt))
            if article:
                article['_provider'] = 'gemini-cli'
                return article
        except Exception as e:
            logger.warning(f"Gemini CLI failed: {e}")

    # Fallback: Gemini API (gemini-2.5-pro)
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
                {'title': a.get('title', ''), 'slug': a.get('slug', ''), 'topic': a.get('topic', '')}
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

        # Collect real search data for this topic
        search_context = None
        try:
            from scripts.fetch_search_queries import enrich_topic_with_search_data
            search_context = enrich_topic_with_search_data(topic)
        except Exception as e:
            logger.warning(f"Search enrichment failed for '{topic}': {e}")

        # Skip topics with zero search demand (no one is searching for this)
        ac_count = len(search_context.get('autocomplete', [])) if search_context else 0
        if ac_count == 0:
            logger.info(f"Skipping topic with 0 autocomplete results (no search demand): {topic}")
            continue

        source_url = topic_data.get('url', '')
        article = generate_article(
            topic,
            existing_articles=existing_articles_for_links,
            source_url=source_url,
            author_name=author_name,
            search_context=search_context,
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
