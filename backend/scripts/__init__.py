"""
WordPress AdSense Automation Scripts

This package contains modules for automated blog content generation and publishing
with Google AdSense monetization.
"""

__version__ = "1.0.0"
__author__ = "WordPress AdSense Automation"

from .fetch_trending import (
    fetch_google_trends,
    fetch_reddit_hot,
)
from .generate_content import generate_article
from .optimize_adsense import optimize_ad_placement

__all__ = [
    'fetch_google_trends',
    'fetch_reddit_hot',
    'generate_article',
    'optimize_adsense',
]
