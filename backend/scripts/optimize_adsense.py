"""
AdSense Optimizer

Strategically inserts Google AdSense ad codes into article HTML
for maximum revenue while maintaining user experience.
"""

import logging
import re
from typing import Dict, Optional, List
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_adsense_code(
    client_id: str,
    slot_id: str,
    style: str = "display:block",
    format: str = "auto",
    responsive: bool = True
) -> str:
    """
    Create AdSense ad unit HTML code.

    Args:
        client_id: AdSense client ID (ca-pub-XXXXXXXX)
        slot_id: Ad slot ID
        style: CSS style for ad container
        format: Ad format (auto, rectangle, horizontal, vertical)
        responsive: Whether ad is responsive

    Returns:
        HTML code for AdSense ad unit
    """
    responsive_attr = "true" if responsive else "false"

    ad_code = f"""
<div class="adsense-ad" style="text-align:center; margin: 30px 0;">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client_id}"
        crossorigin="anonymous"></script>
    <ins class="adsbygoogle"
        style="{style}"
        data-ad-client="{client_id}"
        data-ad-slot="{slot_id}"
        data-ad-format="{format}"
        data-full-width-responsive="{responsive_attr}"></ins>
    <script>
        (adsbygoogle = window.adsbygoogle || []).push({{}});
    </script>
</div>
"""
    return ad_code.strip()


def find_insertion_points(html_content: str) -> Dict[str, int]:
    """
    Find optimal positions to insert ads in HTML content.

    Args:
        html_content: Article HTML content

    Returns:
        Dictionary with insertion point positions:
        {
            'after_intro': int,
            'mid_content': int,
            'before_conclusion': int
        }
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Get all major content blocks (paragraphs and headings)
    paragraphs = soup.find_all(['p', 'h2', 'h3'])

    total_blocks = len(paragraphs)

    if total_blocks < 3:
        logger.warning("Article too short for optimal ad placement")
        return {
            'after_intro': 0,
            'mid_content': 0,
            'before_conclusion': 0
        }

    # Calculate positions
    # After intro: After first 2-3 paragraphs
    after_intro_idx = min(2, total_blocks // 4)

    # Mid-content: Around middle
    mid_content_idx = total_blocks // 2

    # Before conclusion: 80-90% through content
    before_conclusion_idx = int(total_blocks * 0.85)

    insertion_points = {
        'after_intro': after_intro_idx,
        'mid_content': mid_content_idx,
        'before_conclusion': before_conclusion_idx
    }

    logger.info(f"Insertion points calculated: {insertion_points}")

    return insertion_points


def optimize_ad_placement(
    article_html: str,
    adsense_config: Dict,
    ad_positions: Optional[Dict[str, bool]] = None
) -> str:
    """
    Insert AdSense ads at optimal positions in article HTML.

    Args:
        article_html: Original article HTML content
        adsense_config: Configuration with client_id and slots
        ad_positions: Which positions to enable (default: all enabled)
                     {'after_intro': True, 'mid_content': True, 'before_conclusion': True}

    Returns:
        Optimized HTML with AdSense codes inserted
    """
    if not adsense_config or 'client_id' not in adsense_config:
        logger.error("Invalid AdSense configuration")
        return article_html

    if ad_positions is None:
        ad_positions = {
            'after_intro': True,
            'mid_content': True,
            'before_conclusion': True
        }

    logger.info("Optimizing ad placement in article")

    try:
        soup = BeautifulSoup(article_html, 'html.parser')

        # Get all major content blocks
        blocks = soup.find_all(['p', 'h2', 'h3', 'ul', 'ol'])

        if len(blocks) < 3:
            logger.warning("Article too short for ad insertion")
            return article_html

        # Find insertion points
        insertion_points = find_insertion_points(article_html)

        # Get ad slot IDs from config
        slots = adsense_config.get('slots', {})
        client_id = adsense_config['client_id']

        # Insert ads at calculated positions (in reverse to maintain indices)
        positions_to_insert = []

        if ad_positions.get('before_conclusion') and 'sidebar' in slots:
            positions_to_insert.append((
                insertion_points['before_conclusion'],
                create_adsense_code(client_id, slots['sidebar'], format='auto')
            ))

        if ad_positions.get('mid_content') and 'in_article' in slots:
            positions_to_insert.append((
                insertion_points['mid_content'],
                create_adsense_code(client_id, slots['in_article'], format='fluid')
            ))

        if ad_positions.get('after_intro') and 'header' in slots:
            positions_to_insert.append((
                insertion_points['after_intro'],
                create_adsense_code(client_id, slots['header'], format='auto')
            ))

        # Sort by position (descending) to maintain correct indices
        positions_to_insert.sort(key=lambda x: x[0], reverse=True)

        # Insert ads
        for position, ad_code in positions_to_insert:
            if position < len(blocks):
                ad_soup = BeautifulSoup(ad_code, 'html.parser')
                blocks[position].insert_after(ad_soup)
                logger.info(f"Inserted ad at position {position}")

        optimized_html = str(soup)

        # Count inserted ads
        ad_count = optimized_html.count('adsbygoogle')
        logger.info(f"Successfully inserted {ad_count} ad units")

        return optimized_html

    except Exception as e:
        logger.error(f"Error optimizing ad placement: {str(e)}")
        return article_html


def validate_adsense_config(config: Dict) -> bool:
    """
    Validate AdSense configuration.

    Args:
        config: AdSense configuration dictionary

    Returns:
        True if valid, False otherwise
    """
    if not config:
        logger.error("AdSense config is empty")
        return False

    if 'client_id' not in config:
        logger.error("Missing client_id in AdSense config")
        return False

    client_id = config['client_id']
    if not client_id.startswith('ca-pub-'):
        logger.error(f"Invalid AdSense client ID format: {client_id}")
        return False

    if 'slots' not in config:
        logger.warning("No ad slots defined in config")
        return True  # Still valid, just no ads will be inserted

    slots = config['slots']
    if not isinstance(slots, dict) or len(slots) == 0:
        logger.warning("Ad slots is empty or invalid")
        return True

    logger.info(f"AdSense config validated: {len(slots)} slots available")
    return True


def remove_ads(html_content: str) -> str:
    """
    Remove all AdSense ad codes from HTML content.

    Args:
        html_content: HTML with ads

    Returns:
        HTML without ads
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove all ad containers
    for ad in soup.find_all('div', class_='adsense-ad'):
        ad.decompose()

    # Remove any leftover AdSense scripts
    for script in soup.find_all('script', src=re.compile(r'adsbygoogle')):
        script.decompose()

    return str(soup)


if __name__ == "__main__":
    # Test the ad optimization
    print("Testing AdSense optimization...\n")

    # Sample article HTML
    sample_html = """
<h2>Introduction to AI</h2>
<p>Artificial Intelligence is transforming our world.</p>
<p>This technology has numerous applications across industries.</p>

<h2>Key Benefits</h2>
<p>AI provides automation and efficiency improvements.</p>
<p>It can process vast amounts of data quickly.</p>
<p>Machine learning enables continuous improvement.</p>

<h2>Applications</h2>
<p>Healthcare is seeing significant AI adoption.</p>
<p>Financial services use AI for fraud detection.</p>
<p>Retail leverages AI for personalization.</p>

<h2>Future Outlook</h2>
<p>AI will continue to evolve and improve.</p>
<p>We can expect more sophisticated applications.</p>
<p>The future of AI is bright and promising.</p>
"""

    # Sample AdSense config
    test_config = {
        'client_id': 'ca-pub-1234567890123456',
        'slots': {
            'header': '1111111111',
            'in_article': '2222222222',
            'sidebar': '3333333333'
        }
    }

    # Validate config
    if validate_adsense_config(test_config):
        print("✓ AdSense config is valid\n")

    # Optimize ad placement
    print("Original HTML length:", len(sample_html))
    optimized = optimize_ad_placement(sample_html, test_config)
    print("Optimized HTML length:", len(optimized))

    # Count ads
    ad_count = optimized.count('adsbygoogle')
    print(f"\n✓ Inserted {ad_count} ad units")

    print("\nOptimized HTML preview (first 500 chars):")
    print(optimized[:500] + "...")
