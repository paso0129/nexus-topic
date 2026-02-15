"""
Backfill missing trending_sources for existing articles.

Searches article titles against all trending source APIs to find matches,
then inserts the source data into the trending_sources table.

Usage:
  python scripts/backfill_sources.py [--dry-run]
"""

import os
import sys
import re
import logging
import argparse
from datetime import datetime

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

supabase = create_client(
    os.environ['SUPABASE_URL'],
    os.environ['SUPABASE_SERVICE_KEY']
)


def normalize(text: str) -> set:
    """Extract significant words for comparison."""
    return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) > 2}


def similarity(a: str, b: str) -> float:
    """Jaccard similarity between two strings."""
    words_a = normalize(a)
    words_b = normalize(b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def fetch_hackernews_titles(limit=30):
    """Fetch recent HackerNews top story titles."""
    try:
        resp = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10)
        ids = resp.json()[:limit]
        results = []
        for sid in ids:
            r = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5)
            story = r.json()
            if story and 'title' in story:
                results.append({
                    'title': story['title'],
                    'source': 'hackernews',
                    'score': story.get('score', 0),
                    'url': story.get('url', f'https://news.ycombinator.com/item?id={sid}'),
                })
        return results
    except Exception as e:
        logger.warning(f"HN fetch failed: {e}")
        return []


def fetch_devto_titles(limit=30):
    try:
        resp = requests.get('https://dev.to/api/articles', params={'top': 7, 'per_page': limit}, timeout=10)
        return [{'title': a['title'], 'source': 'devto', 'score': a.get('public_reactions_count', 0), 'url': a.get('url', '')} for a in resp.json()]
    except Exception as e:
        logger.warning(f"Dev.to fetch failed: {e}")
        return []


def fetch_rss_titles():
    import xml.etree.ElementTree as ET
    results = []
    feeds = [
        ('https://techcrunch.com/feed/', 'techcrunch'),
        ('https://www.theverge.com/rss/index.xml', 'theverge'),
    ]
    for url, source in feeds:
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            root = ET.fromstring(resp.text)
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('.//item')
            for idx, item in enumerate(items[:30]):
                title = item.find('{http://www.w3.org/2005/Atom}title')
                if title is None:
                    title = item.find('title')
                link = item.find('{http://www.w3.org/2005/Atom}link')
                if link is None:
                    link = item.find('link')
                if title is not None and title.text:
                    link_url = ''
                    if link is not None:
                        link_url = link.get('href', '') or link.text or ''
                    results.append({'title': title.text.strip(), 'source': source, 'score': 30 - idx, 'url': link_url})
        except Exception as e:
            logger.warning(f"{source} RSS failed: {e}")
    return results


def fetch_producthunt_titles():
    import xml.etree.ElementTree as ET
    atom_ns = '{http://www.w3.org/2005/Atom}'
    try:
        resp = requests.get('https://www.producthunt.com/feed', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        root = ET.fromstring(resp.text)
        entries = root.findall(f'{atom_ns}entry')
        results = []
        for idx, entry in enumerate(entries[:20]):
            title = entry.find(f'{atom_ns}title')
            link = entry.find(f'{atom_ns}link')
            if title is not None and title.text:
                results.append({'title': title.text, 'source': 'producthunt', 'score': 20 - idx, 'url': link.get('href', '') if link is not None else ''})
        return results
    except Exception as e:
        logger.warning(f"PH fetch failed: {e}")
        return []


def fetch_google_trends_titles():
    import xml.etree.ElementTree as ET
    results = []
    for geo in ['US', 'UK', 'CA']:
        try:
            resp = requests.get(f'https://trends.google.com/trending/rss?geo={geo}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            root = ET.fromstring(resp.text)
            for idx, item in enumerate(root.findall('.//item/title')[:15]):
                if item.text:
                    results.append({'title': item.text, 'source': 'google_trends', 'score': 15 - idx, 'url': ''})
        except Exception as e:
            logger.warning(f"Google Trends {geo} failed: {e}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Only show matches, do not insert')
    parser.add_argument('--threshold', type=float, default=0.35, help='Similarity threshold (default 0.35)')
    args = parser.parse_args()

    # 1. Get articles without source
    logger.info("Fetching articles without source data...")
    all_articles = supabase.table('articles').select('id, slug, title').eq('published', True).execute().data or []
    existing_sources = supabase.table('trending_sources').select('article_id').execute().data or []
    existing_ids = {s['article_id'] for s in existing_sources}

    missing = [a for a in all_articles if a['id'] not in existing_ids]
    logger.info(f"Found {len(missing)} articles without source (out of {len(all_articles)} total)")

    if not missing:
        logger.info("All articles have source data. Nothing to do.")
        return

    # 2. Fetch all source titles
    logger.info("Fetching titles from all sources...")
    all_sources = []
    all_sources.extend(fetch_hackernews_titles())
    all_sources.extend(fetch_devto_titles())
    all_sources.extend(fetch_rss_titles())
    all_sources.extend(fetch_producthunt_titles())
    all_sources.extend(fetch_google_trends_titles())
    logger.info(f"Fetched {len(all_sources)} source titles")

    # 3. Match articles to sources
    matched = 0
    unmatched = 0
    for article in missing:
        best_match = None
        best_score = 0.0

        for src in all_sources:
            sim = similarity(article['title'], src['title'])
            if sim > best_score:
                best_score = sim
                best_match = src

        if best_match and best_score >= args.threshold:
            matched += 1
            logger.info(f"  MATCH ({best_score:.2f}): \"{article['title'][:50]}\" → {best_match['source']} (\"{best_match['title'][:50]}\")")

            if not args.dry_run:
                try:
                    supabase.table('trending_sources').insert({
                        'article_id': article['id'],
                        'keyword': best_match['title'],
                        'source': best_match['source'],
                        'score': best_match.get('score', 0),
                        'region': 'global',
                        'url': best_match.get('url'),
                        'timestamp': datetime.utcnow().isoformat(),
                    }).execute()
                except Exception as e:
                    logger.warning(f"  Failed to insert source for {article['slug']}: {e}")
        else:
            unmatched += 1
            if best_match:
                logger.info(f"  NO MATCH ({best_score:.2f}): \"{article['title'][:60]}\" (best: {best_match['source']})")
            else:
                logger.info(f"  NO MATCH: \"{article['title'][:60]}\"")

    logger.info(f"\nDone! Matched: {matched}, Unmatched: {unmatched}")
    if args.dry_run:
        logger.info("(dry run - no changes made)")


if __name__ == '__main__':
    main()
