"""
Validate external links in generated article HTML content.

Checks each external link via HTTP HEAD/GET requests.
Removes broken links (404), fixes known domain typos,
and auto-corrects Wikipedia URL casing via redirects.
"""

import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

import requests

logger = logging.getLogger(__name__)

# Known domain typos: wrong → correct
DOMAIN_TYPO_MAP = {
    "www.ars.com": "arstechnica.com",
    "ars.com": "arstechnica.com",
    "www.the-independent.com": "www.independent.co.uk",
    "the-independent.com": "www.independent.co.uk",
    "www.techcrunch.co": "techcrunch.com",
    "www.theguardian.co": "www.theguardian.com",
    "www.bbc.co": "www.bbc.co.uk",
    "wired.co": "www.wired.com",
    "www.reuterss.com": "www.reuters.com",
    "www.forbe.com": "www.forbes.com",
    "www.forbs.com": "www.forbes.com",
    "engaget.com": "www.engadget.com",
    "www.engaget.com": "www.engadget.com",
    "www.theverge.co": "www.theverge.com",
    "mashable.co": "mashable.com",
}

INTERNAL_PATTERNS = [
    "nexustopic.com",
    "/article/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
}

TIMEOUT = 8
MAX_WORKERS = 5

# Regex to match <a> tags with href
LINK_RE = re.compile(
    r'<a\s+([^>]*?)href=["\']([^"\']+)["\']([^>]*?)>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _is_internal(url: str) -> bool:
    """Check if a URL is internal (skip validation)."""
    for pattern in INTERNAL_PATTERNS:
        if pattern in url:
            return True
    if url.startswith("/") and not url.startswith("//"):
        return True
    return False


def _fix_domain_typo(url: str) -> Optional[str]:
    """Fix known domain typos. Returns corrected URL or None."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host in DOMAIN_TYPO_MAP:
            corrected_host = DOMAIN_TYPO_MAP[host]
            corrected = parsed._replace(netloc=corrected_host)
            return urlunparse(corrected)
    except Exception:
        pass
    return None


def _check_link(url: str) -> Dict:
    """
    Check a single URL via HEAD then GET.

    Returns dict with:
        url: original URL
        status: HTTP status code or error string
        action: 'keep', 'remove', 'fix'
        fixed_url: corrected URL if action is 'fix'
    """
    result = {"url": url, "status": None, "action": "keep", "fixed_url": None}

    # Step 1: Fix known domain typos before requesting
    fixed = _fix_domain_typo(url)
    if fixed:
        logger.info(f"  Domain typo: {url} → {fixed}")
        result["action"] = "fix"
        result["fixed_url"] = fixed
        url = fixed  # validate the corrected URL

    try:
        # HEAD first (lightweight)
        resp = requests.head(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        status = resp.status_code

        # Wikipedia redirect → auto-correct URL casing
        if "wikipedia.org" in url and resp.url != url:
            result["action"] = "fix"
            result["fixed_url"] = resp.url
            logger.info(f"  Wikipedia redirect: {url} → {resp.url}")

        if status == 404:
            result["status"] = 404
            result["action"] = "remove"
            return result

        if status in (401, 403):
            result["status"] = status
            # Bot-blocked: treat as valid
            return result

        if status == 405 or status >= 500:
            # HEAD not allowed or server error — try GET
            raise requests.exceptions.RequestException("HEAD rejected")

        result["status"] = status
        return result

    except requests.exceptions.RequestException:
        pass

    # GET fallback
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True
        )
        resp.close()
        status = resp.status_code

        if "wikipedia.org" in url and resp.url != url:
            result["action"] = "fix"
            result["fixed_url"] = resp.url
            logger.info(f"  Wikipedia redirect: {url} → {resp.url}")

        if status == 404:
            result["status"] = 404
            result["action"] = "remove"
        elif status in (401, 403):
            result["status"] = status
        else:
            result["status"] = status

        return result

    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        logger.warning(f"  Timeout: {url} (keeping)")
        return result

    except requests.exceptions.ConnectionError:
        result["status"] = "connection_error"
        logger.warning(f"  Connection error: {url} (keeping)")
        return result

    except Exception as e:
        result["status"] = f"error: {e}"
        logger.warning(f"  Error checking {url}: {e} (keeping)")
        return result


def _apply_fixes(content: str, check_results: List[Dict]) -> Tuple[str, int, int]:
    """
    Apply link fixes/removals to HTML content.

    Returns (modified_content, removed_count, fixed_count).
    """
    removed = 0
    fixed = 0

    for r in check_results:
        if r["action"] == "remove":
            # Replace <a href="URL">text</a> with just text
            pattern = re.compile(
                r'<a\s+[^>]*?href=["\']'
                + re.escape(r["url"])
                + r'["\'][^>]*?>(.*?)</a>',
                re.IGNORECASE | re.DOTALL,
            )
            new_content = pattern.sub(r"\1", content)
            if new_content != content:
                content = new_content
                removed += 1
                logger.info(f"  ✗ Removed broken link: {r['url']}")

        elif r["action"] == "fix" and r["fixed_url"]:
            old_url = r["url"]
            new_url = r["fixed_url"]
            if old_url != new_url and old_url in content:
                content = content.replace(old_url, new_url)
                fixed += 1
                logger.info(f"  ✓ Fixed link: {old_url} → {new_url}")

    return content, removed, fixed


def validate_article_links(articles: list) -> list:
    """
    Validate all external links in article HTML content.

    - Removes 404 links (keeps anchor text)
    - Fixes known domain typos
    - Auto-corrects Wikipedia URL casing
    - Parallel checking with ThreadPoolExecutor

    Args:
        articles: list of article dicts with 'content' key

    Returns:
        Modified articles list
    """
    logger.info("Validating external links in articles...")

    total_removed = 0
    total_fixed = 0
    total_checked = 0

    for idx, article in enumerate(articles, 1):
        title = article.get("title", f"Article {idx}")
        content = article.get("content", "")

        if not content:
            continue

        # Extract all links
        matches = LINK_RE.findall(content)
        external_urls = []
        seen = set()

        for pre_attrs, href, post_attrs, _text in matches:
            if href in seen or _is_internal(href):
                continue
            if not href.startswith(("http://", "https://")):
                continue
            seen.add(href)
            external_urls.append(href)

        if not external_urls:
            logger.info(f"  [{idx}] {title}: no external links")
            continue

        logger.info(f"  [{idx}] {title}: checking {len(external_urls)} external links")

        # Check links in parallel
        check_results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(_check_link, url): url for url in external_urls
            }
            for future in as_completed(future_map):
                result = future.result()
                check_results.append(result)

        total_checked += len(check_results)

        # Apply fixes
        content, removed, fixed = _apply_fixes(content, check_results)
        article["content"] = content
        total_removed += removed
        total_fixed += fixed

    logger.info(
        f"Link validation complete: {total_checked} checked, "
        f"{total_fixed} fixed, {total_removed} removed"
    )

    return articles
