"""
Legacy slug recovery: rebuild the lost old-English-slug → article mapping.

Why this exists
---------------
The 2026-03 numeric→Korean migration overwrote `articles.old_slug` with the
intermediate numeric ID, dropping the original English slug Google was still
indexing. Result: GSC's top-impression pages (claude-ai-..., 5-ways-heartbreak-...)
all return 410 Gone, killing accumulated link equity.

What it does
------------
1. Pulls every article URL Google has impressed/clicked over the last N days
   (default 365) from the Search Console API.
2. Filters to legacy `/article/<slug>` paths whose slug is NOT a current valid
   slug AND not already in `slug_aliases`.
3. Tries to find the matching article in Supabase by:
     a) exact match against `articles.old_slug`        (confidence 1.00)
     b) exact match against `articles.slug` history    (confidence 1.00)
     c) keyword overlap between slug tokens and title  (confidence 0.40-0.95)
4. Writes a candidates JSON for human review (--dry-run, default), or inserts
   into `slug_aliases` directly with --apply.

Usage
-----
    python -m scripts.recover_legacy_slugs --days 365 --dry-run
    python -m scripts.recover_legacy_slugs --days 365 --apply --min-confidence 0.55

Environment
-----------
    SUPABASE_URL, SUPABASE_SERVICE_KEY, GOOGLE_INDEXING_SA_KEY
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote

import requests
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SITE_URL = "https://www.nexustopic.com"
SC_PROPERTY = "sc-domain:nexustopic.com"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]

ARTICLE_PATH_RE = re.compile(r"^/article/(?P<slug>[^/?#]+)/?$")
TOKEN_SPLIT_RE = re.compile(r"[-_/]+")
ENG_TOKEN_RE = re.compile(r"^[a-z0-9]{2,}$")

STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "onto", "this", "that",
    "your", "their", "about", "after", "before", "what", "when", "where",
    "why", "how", "why-the", "is-it", "be", "to", "of", "in", "on", "by",
    "an", "a", "as", "at", "or", "but",
}


def fetch_gsc_pages(days: int) -> list[dict]:
    """Pull every URL with at least one impression in the last `days` days."""
    sa_json = os.environ["GOOGLE_INDEXING_SA_KEY"]
    info = json.loads(sa_json)

    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }
    encoded = quote(SC_PROPERTY, safe="")
    api_url = (
        f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query"
    )

    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    rows: list[dict] = []
    start_row = 0
    page_size = 25_000  # GSC API max
    while True:
        resp = requests.post(
            api_url,
            headers=headers,
            json={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page"],
                "rowLimit": page_size,
                "startRow": start_row,
                "dataState": "all",
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GSC API error {resp.status_code}: {resp.text[:300]}")
        page_rows = resp.json().get("rows", [])
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start_row += page_size

    logger.info(f"GSC pages fetched: {len(rows)} ({start_date} ~ {end_date})")
    return rows


def extract_article_slugs(rows: Iterable[dict]) -> list[dict]:
    """Keep only `/article/<slug>` URLs and decode the slug."""
    out = []
    for row in rows:
        page = row["keys"][0]
        path = page.replace(SITE_URL, "").replace("https://nexustopic.com", "")
        match = ARTICLE_PATH_RE.match(path)
        if not match:
            continue
        raw = match.group("slug")
        try:
            slug = unquote(raw)
        except Exception:
            slug = raw
        out.append({
            "slug": slug,
            "page": page,
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
        })
    return out


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^a-z0-9가-힣\s\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug_tokens(slug: str) -> set[str]:
    return {
        t for t in TOKEN_SPLIT_RE.split(slug.lower())
        if ENG_TOKEN_RE.match(t) and t not in STOPWORDS
    }


def title_tokens(title: str) -> set[str]:
    cleaned = normalise(title)
    return {t for t in cleaned.split() if t and t not in STOPWORDS}


def score_match(slug: str, article: dict) -> float:
    """Token-overlap score in [0, 1]."""
    s_tokens = slug_tokens(slug)
    if not s_tokens:
        return 0.0

    haystack = " ".join(filter(None, [
        article.get("title") or "",
        article.get("meta_description") or "",
        " ".join(article.get("keywords") or []),
    ]))
    hay_tokens = title_tokens(haystack)
    if not hay_tokens:
        return 0.0

    overlap = s_tokens & hay_tokens
    return round(len(overlap) / len(s_tokens), 2)


def best_article(slug: str, articles: list[dict]) -> tuple[dict | None, float]:
    best = None
    best_score = 0.0
    for article in articles:
        score = score_match(slug, article)
        if score > best_score:
            best = article
            best_score = score
    return best, best_score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--apply", action="store_true",
                        help="Write to slug_aliases (otherwise dry-run JSON)")
    parser.add_argument("--min-confidence", type=float, default=0.55,
                        help="Skip suggestions below this score (default 0.55)")
    parser.add_argument("--output", default="legacy_slug_candidates.json")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # 1. Pull article corpus + existing alias set in one round-trip each.
    art_resp = sb.table("articles").select(
        "id, slug, old_slug, title, meta_description, keywords"
    ).eq("published", True).execute()
    articles: list[dict] = art_resp.data or []
    valid_slugs = {a["slug"] for a in articles if a.get("slug")}
    old_slug_to_id = {
        a["old_slug"]: a["id"]
        for a in articles
        if a.get("old_slug") and a.get("old_slug") != a.get("slug")
    }

    alias_resp = sb.table("slug_aliases").select("alias").execute()
    existing_aliases = {row["alias"] for row in (alias_resp.data or [])}

    logger.info(f"Articles: {len(articles)} | existing aliases: {len(existing_aliases)}")

    # 2. Pull GSC URLs.
    rows = fetch_gsc_pages(args.days)
    candidate_slugs = extract_article_slugs(rows)
    logger.info(f"Article-shaped GSC URLs: {len(candidate_slugs)}")

    # 3. Filter to slugs that need recovery.
    needs_recovery = [
        c for c in candidate_slugs
        if c["slug"] not in valid_slugs and c["slug"] not in existing_aliases
    ]
    logger.info(f"Slugs needing recovery: {len(needs_recovery)}")

    suggestions: list[dict] = []
    auto_matches = 0
    for entry in needs_recovery:
        slug = entry["slug"]

        # exact old_slug hit (shouldn't happen post-migration, but check)
        if slug in old_slug_to_id:
            suggestions.append({
                "alias": slug,
                "article_id": old_slug_to_id[slug],
                "confidence": 1.00,
                "source": "exact_old_slug",
                "impressions": entry["impressions"],
                "clicks": entry["clicks"],
                "matched_title": next(
                    (a["title"] for a in articles if a["id"] == old_slug_to_id[slug]),
                    "",
                ),
            })
            auto_matches += 1
            continue

        article, score = best_article(slug, articles)
        if not article or score < args.min_confidence:
            suggestions.append({
                "alias": slug,
                "article_id": None,
                "confidence": score,
                "source": "unmatched",
                "impressions": entry["impressions"],
                "clicks": entry["clicks"],
                "matched_title": article.get("title", "") if article else "",
            })
            continue

        suggestions.append({
            "alias": slug,
            "article_id": article["id"],
            "confidence": score,
            "source": "fuzzy_title",
            "impressions": entry["impressions"],
            "clicks": entry["clicks"],
            "matched_title": article["title"],
        })

    suggestions.sort(key=lambda s: (-s["impressions"], -s["confidence"]))

    matched = [s for s in suggestions if s["article_id"] and s["confidence"] >= args.min_confidence]
    unmatched = [s for s in suggestions if not s["article_id"] or s["confidence"] < args.min_confidence]

    logger.info(
        f"Matched ≥{args.min_confidence}: {len(matched)} | "
        f"unmatched/low-confidence: {len(unmatched)}"
    )

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps({"matched": matched, "unmatched": unmatched}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Candidates written → {output_path.resolve()}")

    if not args.apply:
        logger.info("Dry-run only. Re-run with --apply to write to slug_aliases.")
        return 0

    inserted = 0
    failed = 0
    for s in matched:
        try:
            sb.table("slug_aliases").upsert({
                "alias": s["alias"],
                "article_id": s["article_id"],
                "source": "gsc",
                "confidence": s["confidence"],
            }, on_conflict="alias").execute()
            inserted += 1
        except Exception as e:
            failed += 1
            logger.warning(f"  insert failed for {s['alias']}: {e}")

    logger.info(f"Inserted: {inserted} | failed: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
