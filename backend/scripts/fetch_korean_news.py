"""
Korean News RSS Trending Fetcher

Collects trending topics from Korean news outlets:
- SBS 뉴스 인기기사 (popular/headline)
- 한국경제 카테고리별
- 매일경제 카테고리별
- 네이버 데이터랩 급상승 검색어 (HTML scraping)
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Dict
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


def _get_text_utf8(resp: requests.Response) -> str:
    """Force UTF-8 decoding for RSS responses (requests often misdetects charset)."""
    try:
        return resp.content.decode('utf-8')
    except UnicodeDecodeError:
        return resp.content.decode('euc-kr', errors='replace')

# Category mapping: NexusTopic category → RSS feeds
KOREAN_RSS_FEEDS = {
    '경제': [
        ('sbs_economy', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER'),
        ('hankyung_economy', 'https://www.hankyung.com/feed/economy'),
        ('hankyung_finance', 'https://www.hankyung.com/feed/finance'),
    ],
    'IT·테크': [
        ('hankyung_it', 'https://www.hankyung.com/feed/it'),
        ('etnews_popular', 'http://rss.etnews.com/Section903.xml'),
        ('etnews_sw_ai', 'http://rss.etnews.com/04046.xml'),
    ],
    '글로벌 경제': [
        ('hankyung_international', 'https://www.hankyung.com/feed/international'),
        ('sbs_international', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07&plink=RSSREADER'),
    ],
    '부동산': [
        ('hankyung_realestate', 'https://www.hankyung.com/feed/realestate'),
    ],
    '연예': [
        ('sbs_entertainment', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=14&plink=RSSREADER'),
        ('hankyung_entertainment', 'https://www.hankyung.com/feed/entertainment'),
    ],
    '스포츠': [
        ('sbs_sports', 'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=09&plink=RSSREADER'),
        ('hankyung_sports', 'https://www.hankyung.com/feed/sports'),
    ],
}

# SBS 인기뉴스 (all categories, popular articles)
SBS_POPULAR_FEED = 'https://news.sbs.co.kr/news/TopicRssFeed.do?plink=RSSREADER'

# Global tech media RSS — Apple/Samsung/Google product launches
GLOBAL_TECH_FEEDS = [
    ('theverge', 'https://www.theverge.com/rss/index.xml'),
    ('techcrunch', 'https://techcrunch.com/feed/'),
    ('arstechnica', 'https://feeds.arstechnica.com/arstechnica/index'),
]


def _parse_rss(xml_text: str, source_name: str, limit: int = 5) -> List[Dict]:
    """Parse RSS/Atom XML and extract article titles as trending topics."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Handle both RSS (<item>) and Atom (<entry>) formats
        atom_ns = '{http://www.w3.org/2005/Atom}'
        entries = root.findall('.//item')
        if not entries:
            entries = root.findall(f'.//{atom_ns}entry')
        for idx, item in enumerate(entries):
            if len(items) >= limit:
                break
            # RSS: <title>, Atom: <title> (with namespace)
            # NOTE: do NOT use `el or fallback` — bool(Element) is False when element has no children
            title_el = item.find('title')
            if title_el is None:
                title_el = item.find(f'{atom_ns}title')
            link_el = item.find('link')
            if link_el is None:
                link_el = item.find(f'{atom_ns}link')
            desc_el = item.find('description')
            if desc_el is None:
                desc_el = item.find(f'{atom_ns}summary')

            title = title_el.text.strip() if title_el is not None and title_el.text else ''
            if not title or len(title) < 5:
                continue

            # Clean CDATA and HTML
            title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
            title = re.sub(r'<[^>]+>', '', title).strip()

            # RSS: <link>url</link>, Atom: <link href="url"/>
            link = ''
            if link_el is not None:
                link = link_el.get('href', '') or (link_el.text.strip() if link_el.text else '')
            desc = ''
            if desc_el is not None and desc_el.text:
                desc = re.sub(r'<[^>]+>', '', desc_el.text).strip()[:200]

            items.append({
                'keyword': title,
                'source': source_name,
                'score': max(limit - idx, 1) * 10,
                'region': 'KR',
                'url': link,
                'description': desc,
                'timestamp': datetime.now().isoformat(),
            })
    except ET.ParseError as e:
        logger.warning(f"XML parse error for {source_name}: {e}")
        logger.warning(f"  First 200 chars: {xml_text[:200]}")
    except Exception as e:
        logger.warning(f"Unexpected error parsing {source_name}: {e}")
    if not items:
        logger.warning(f"  {source_name}: 0 items parsed from {len(xml_text)} chars")
    return items


def fetch_korean_news_rss(limit_per_feed: int = 5) -> List[Dict]:
    """Fetch trending topics from Korean news RSS feeds, organized by category."""
    logger.info("Fetching Korean news RSS feeds...")
    all_topics = []

    # 1. SBS 인기뉴스 (top stories across all categories)
    try:
        resp = requests.get(SBS_POPULAR_FEED, timeout=15,
                           headers={'User-Agent': 'Mozilla/5.0 (compatible; NexusTopic/1.0)'})
        resp.raise_for_status()
        text = _get_text_utf8(resp)
        logger.info(f"  SBS response: {resp.status_code}, length={len(text)}, starts={text[:100]}")
        popular = _parse_rss(text, 'sbs_popular', limit=8)
        all_topics.extend(popular)
        logger.info(f"  SBS 인기뉴스: {len(popular)} topics")
    except Exception as e:
        logger.warning(f"  SBS 인기뉴스 failed: {e}")

    # 2. Category-specific feeds
    for category, feeds in KOREAN_RSS_FEEDS.items():
        cat_count = 0
        for source_name, url in feeds:
            try:
                resp = requests.get(url, timeout=15,
                                   headers={'User-Agent': 'Mozilla/5.0 (compatible; NexusTopic/1.0)'})
                resp.raise_for_status()
                text = _get_text_utf8(resp)
                if len(text) < 100:
                    logger.warning(f"  {source_name}: short response ({len(text)} chars): {text[:80]}")
                items = _parse_rss(text, source_name, limit=limit_per_feed)
                # Tag with category
                for item in items:
                    item['_quick_cat'] = category
                all_topics.extend(items)
                cat_count += len(items)
            except Exception as e:
                logger.warning(f"  {source_name} failed: {e}")
        logger.info(f"  {category}: {cat_count} topics")

    logger.info(f"Total Korean news topics: {len(all_topics)}")
    return all_topics


def fetch_naver_datalab_trends() -> List[Dict]:
    """Naver DataLab is discontinued (404). Returns empty list."""
    return []


def fetch_global_tech_rss(limit_per_feed: int = 5) -> List[Dict]:
    """Fetch trending topics from global tech media. RSS 상위 = 최신/중요 기사."""
    logger.info("Fetching global tech RSS feeds...")
    all_topics = []

    for source_name, url in GLOBAL_TECH_FEEDS:
        try:
            resp = requests.get(url, timeout=15,
                               headers={'User-Agent': 'Mozilla/5.0 (compatible; NexusTopic/1.0)'})
            resp.raise_for_status()
            # RSS 상위 기사 = 가장 중요. _parse_rss가 이미 순서 기반 스코어 부여
            items = _parse_rss(_get_text_utf8(resp), source_name, limit=limit_per_feed)
            for item in items:
                item['_quick_cat'] = 'IT·테크'
            all_topics.extend(items)
            logger.info(f"  {source_name}: {len(items)} topics")
        except Exception as e:
            logger.warning(f"  {source_name} failed: {e}")

    logger.info(f"Global tech topics: {len(all_topics)}")
    return all_topics


def get_korean_trending_topics(limit_per_feed: int = 5) -> List[Dict]:
    """Fetch all trending topics from Korean RSS + DataLab + Global Tech."""
    rss_topics = fetch_korean_news_rss(limit_per_feed=limit_per_feed)
    datalab_topics = fetch_naver_datalab_trends()
    tech_topics = fetch_global_tech_rss(limit_per_feed=5)
    all_topics = rss_topics + datalab_topics + tech_topics
    logger.info(f"Total trending: {len(all_topics)} (KR RSS={len(rss_topics)}, DataLab={len(datalab_topics)}, Global Tech={len(tech_topics)})")
    return all_topics


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    topics = get_korean_trending_topics()
    for t in topics[:30]:
        cat = t.get('_quick_cat', '?')
        print(f"  [{cat:6s}] [{t['source']:25s}] {t['keyword'][:60]}")
