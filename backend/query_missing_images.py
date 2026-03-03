"""Query articles with missing featured images from Supabase."""

import os
import sys
from supabase import create_client

def main():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')

    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        sys.exit(1)

    client = create_client(url, key)

    # Query articles where featured_image is NULL or empty string
    result = client.table('articles') \
        .select('slug,title,topic,featured_image,created_at') \
        .eq('published', True) \
        .or_('featured_image.is.null,featured_image.eq.') \
        .order('created_at', desc=True) \
        .execute()

    articles = result.data
    print(f"\n=== Articles without featured images: {len(articles)} ===\n")

    for i, a in enumerate(articles, 1):
        print(f"{i}. [{a.get('topic', 'N/A')}] {a['title']}")
        print(f"   slug: {a['slug']}")
        print(f"   featured_image: {repr(a.get('featured_image'))}")
        print(f"   created_at: {a.get('created_at', 'N/A')}")
        print()

    # Also count total articles for context
    total = client.table('articles') \
        .select('id', count='exact') \
        .eq('published', True) \
        .execute()
    total_count = total.count if hasattr(total, 'count') and total.count else len(total.data)
    print(f"Total published articles: {total_count}")
    print(f"Articles missing images: {len(articles)}")


if __name__ == '__main__':
    main()
