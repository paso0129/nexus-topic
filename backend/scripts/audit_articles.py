"""
Article Quality Audit Script

Comprehensive quality audit for AdSense approval readiness.
Checks: word count, source links, truncation, keywords, category, images.

Usage:
  python -m scripts.audit_articles                # Full report
  python -m scripts.audit_articles --delete-ids   # Print delete candidate IDs
"""
import os
import re
import json
import argparse
import logging
from collections import Counter
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

MIN_WORD_COUNT = 800
MIN_SOURCES = 2


def count_words(html: str) -> int:
    """Count words (어절) in HTML content."""
    text = re.sub(r'<[^>]+>', '', html)
    return len(text.split())


def count_source_links(content: str) -> int:
    """Count external links in content."""
    return len(re.findall(r'<a\s+[^>]*href=["\']https?://', content))


def is_truncated(html: str) -> bool:
    """Check if article content appears truncated."""
    text = re.sub(r'<[^>]+>', '', html).strip()
    if not text:
        return True
    last_line = text.split('\n')[-1].strip()
    if last_line and last_line[-1] not in '.?!다), 」』, "':
        return True
    return False


def quality_score(word_count: int, source_count: int, has_image: bool) -> int:
    """0-100 quality score. Higher = better."""
    wc_score = min(word_count / 1200, 1.0) * 50
    src_score = min(source_count / 3, 1.0) * 35
    img_score = 15 if has_image else 0
    return round(wc_score + src_score + img_score)


def main():
    parser = argparse.ArgumentParser(description='Article quality audit')
    parser.add_argument('--delete-ids', action='store_true',
                        help='Print comma-separated IDs of delete candidates')
    args = parser.parse_args()

    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    supabase = create_client(url, key)

    result = supabase.table('articles').select(
        'id, slug, title, content, keywords, topic, word_count, published, featured_image, created_at'
    ).eq('published', True).order('created_at', desc=True).execute()
    articles = result.data or []

    # Analyze each article
    analyzed = []
    for a in articles:
        content = a.get('content', '') or ''
        wc = count_words(content)
        sources = count_source_links(content)
        has_image = bool(a.get('featured_image'))
        score = quality_score(wc, sources, has_image)
        topic = a.get('topic', '?')
        truncated = is_truncated(content)

        analyzed.append({
            'id': a['id'],
            'slug': a.get('slug', ''),
            'title': (a.get('title', '') or '')[:60],
            'topic': topic,
            'word_count': wc,
            'sources': sources,
            'score': score,
            'has_image': has_image,
            'truncated': truncated,
            'created_at': (a.get('created_at', '') or '')[:10],
        })

    analyzed.sort(key=lambda x: (x['score'], x['word_count']))

    total = len(analyzed)
    if total == 0:
        logger.info("No published articles found.")
        return

    scores = [a['score'] for a in analyzed]
    word_counts = [a['word_count'] for a in analyzed]
    topic_counts = Counter(a['topic'] for a in analyzed)

    # Quality tiers
    delete_candidates = [a for a in analyzed if a['word_count'] < 500 and a['sources'] == 0]
    poor = [a for a in analyzed if a['score'] < 30 and a not in delete_candidates]
    okay = [a for a in analyzed if 30 <= a['score'] < 60]
    good = [a for a in analyzed if a['score'] >= 60]

    if args.delete_ids:
        ids = [str(a['id']) for a in delete_candidates]
        print(','.join(ids))
        return

    # --- Report ---
    print(f"\n{'=' * 80}")
    print(f"ARTICLE QUALITY AUDIT REPORT")
    print(f"{'=' * 80}")
    print(f"Total published:       {total}")
    print(f"Average score:         {round(sum(scores) / total)}/100")
    print(f"Average word count:    {round(sum(word_counts) / total)}")
    print(f"")

    print(f"--- Quality Tiers ---")
    print(f"  GOOD (score >= 60):     {len(good):3d} ({len(good)*100//total}%)")
    print(f"  OKAY (score 30-59):     {len(okay):3d} ({len(okay)*100//total}%)")
    print(f"  POOR (score < 30):      {len(poor):3d} ({len(poor)*100//total}%)")
    print(f"  DELETE (<500w + 0src):   {len(delete_candidates):3d} ({len(delete_candidates)*100//total}%)")

    print(f"\n--- Category Distribution ---")
    topic_avg = {}
    for topic in topic_counts:
        arts = [a for a in analyzed if a['topic'] == topic]
        topic_avg[topic] = round(sum(a['score'] for a in arts) / len(arts))
    for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
        print(f"  {topic:12s}: {count:3d} articles, avg score {topic_avg[topic]}/100")

    # Word count distribution
    wc_brackets = [(0, 399), (400, 599), (600, 799), (800, 999), (1000, 1499), (1500, 9999)]
    print(f"\n--- Word Count Distribution ---")
    for lo, hi in wc_brackets:
        cnt = len([w for w in word_counts if lo <= w <= hi])
        label = f"{lo}-{hi}" if hi < 9999 else f"{lo}+"
        bar = '#' * (cnt * 40 // total)
        print(f"  {label:>9s}: {cnt:3d} {bar}")

    # Delete candidates
    if delete_candidates:
        print(f"\n--- DELETE CANDIDATES ({len(delete_candidates)}) ---")
        print(f"  <500 words AND 0 sources — low value for AdSense:")
        for a in delete_candidates:
            print(f"  id={a['id']:>5} slug={a['slug']:>5} | {a['word_count']:>4}w | [{a['topic']:8s}] {a['title']}")

    # Poor quality (not delete, but need attention)
    if poor:
        print(f"\n--- POOR QUALITY ({len(poor)}) ---")
        for a in poor[:20]:
            print(
                f"  slug={a['slug']:>5} | score={a['score']:>3} | {a['word_count']:>4}w | "
                f"{a['sources']}src | [{a['topic']:8s}] {a['title']}"
            )
        if len(poor) > 20:
            print(f"  ... and {len(poor) - 20} more")

    print(f"\n{'=' * 80}")
    print(f"RECOMMENDATION:")
    print(f"  1. Delete {len(delete_candidates)} critical articles (<500w + 0 sources)")
    print(f"  2. Monitor {len(poor)} poor articles — new generation will replace them over time")
    print(f"  3. {len(good)} good articles already meet AdSense standards")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
