#!/usr/bin/env python3
"""
Update article dates to today
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from database import get_db_client

load_dotenv()

def update_all_article_dates():
    """Update all article dates to today"""
    db = get_db_client()

    # Get all articles
    articles = db.list_articles(limit=1000, published_only=False)

    today = datetime.now().isoformat()

    print(f"Updating {len(articles)} articles to date: {today}")

    success_count = 0
    for article in articles:
        slug = article.get('slug')
        print(f"Updating {slug}...")

        result = db.update_article(slug, {
            'created_at': today,
            'updated_at': today
        })

        if result:
            success_count += 1
            print(f"  ✓ Updated")
        else:
            print(f"  ✗ Failed")

    print(f"\n✓ Updated {success_count}/{len(articles)} articles")

if __name__ == '__main__':
    update_all_article_dates()
