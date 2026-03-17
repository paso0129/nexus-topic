#!/usr/bin/env python3
"""
AdSense Blog Automation - Main Entry Point

Orchestrates the complete workflow:
1. Fetch trending topics
2. Generate SEO-optimized content
3. Optimize with AdSense placement
4. Save to JSON for Next.js frontend
"""

import argparse
import logging
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv

import re as _re
from collections import defaultdict

from scripts.fetch_trending import get_all_trending_topics
from scripts.generate_content import generate_multiple_articles
from scripts.optimize_adsense import optimize_ad_placement, validate_adsense_config
from scripts.save_article import save_multiple_articles
from scripts.fetch_images import fetch_images_for_articles
from scripts.reclassify import classify_articles
from scripts.validate_links import validate_article_links

# Import database utilities
try:
    from scripts.database import get_db_client, is_supabase_enabled
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not available. Will use JSON-only mode.")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'automation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def validate_environment() -> None:
    """
    Validate environment variables and database connection.
    Checks for required API keys and Supabase configuration.
    """
    import os

    logger.info("\nValidating environment...")

    # Check Gemini CLI availability
    import shutil
    if shutil.which('gemini'):
        logger.info("✓ Gemini CLI found")
    elif os.getenv('GOOGLE_API_KEY'):
        logger.info("✓ Google API key found (Gemini CLI not available, using API)")
    else:
        logger.error("Neither Gemini CLI nor GOOGLE_API_KEY available")
        sys.exit(1)

    # Check Supabase configuration
    if SUPABASE_AVAILABLE and is_supabase_enabled():
        logger.info("✓ Supabase enabled")

        # Check required environment variables
        if not os.getenv('SUPABASE_URL'):
            logger.error("SUPABASE_URL not set in environment")
            sys.exit(1)

        if not os.getenv('SUPABASE_SERVICE_KEY'):
            logger.error("SUPABASE_SERVICE_KEY not set in environment")
            sys.exit(1)

        logger.info("✓ Supabase credentials found")

        # Test database connection
        try:
            db = get_db_client()
            if db.test_connection():
                logger.info("✓ Database connection successful")
                article_count = db.get_article_count()
                logger.info(f"✓ Current articles in database: {article_count}")
            else:
                logger.error("Database connection failed")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            sys.exit(1)
    else:
        logger.info("⊘ Supabase not enabled, using JSON-only mode")

    # Check Gemini image generation capability
    _can_generate_images = os.getenv('GOOGLE_API_KEY') is not None
    try:
        from google import genai as _genai_check
        _can_generate_images = _can_generate_images and True
    except ImportError:
        _can_generate_images = False

    if _can_generate_images:
        logger.info("✓ Gemini image generation available (google-genai + API key)")
    else:
        logger.info("⊘ Gemini image generation not available (needs google-genai + GOOGLE_API_KEY)")

    # Check Unsplash API key (fallback images)
    if os.getenv('UNSPLASH_ACCESS_KEY'):
        logger.info("✓ Unsplash API key found (fallback images)")
    else:
        logger.info("⊘ Unsplash API key not set (fallback images disabled)")

    logger.info("Environment validation complete\n")


def load_config(config_path: str = 'config.yaml') -> Dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config file: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Category-balanced topic selection
# ---------------------------------------------------------------------------

ALL_CATEGORIES = [
    '경제', 'IT·테크', '글로벌 경제', '정치', '사회', '글로벌 사회', '부동산', '연예', '스포츠',
]

_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    '경제': [
        '주가', '코스피', '코스닥', '한국은행', '기준금리', '물가', '수출',
        '원화', '국채', '증시', '상장', '실적', '매출', '영업이익',
        '삼성전자', '현대차', 'SK', 'LG', '카카오', '네이버',
        '금리', '환율', '인플레이션', '경기', '소비자물가', '고용',
    ],
    'IT·테크': [
        '삼성', '애플', '반도체', 'AI', 'GPU', 'SK하이닉스', '엔비디아',
        '네이버', '카카오', 'iphone', 'galaxy', '인공지능', 'chatgpt',
        'openai', 'llm', '클라우드', 'aws', '소프트웨어', '스타트업',
        '로봇', '드론', '자율주행', '배터리', '디스플레이', '5g',
        'semiconductor', 'nvidia', 'apple', 'google', 'microsoft',
    ],
    '글로벌 경제': [
        '나스닥', 's&p500', '연준', '트럼프', '관세', '달러', '유가',
        '비트코인', '이더리움', '암호화폐', '무역전쟁', '중국경제',
        'nasdaq', 'fed', 'bitcoin', 'crypto', 'oil', 'trade war',
        '다우', '엔화', '유로', '금값', '원유', '미국경제',
        'etf', '선물', '옵션', '공매도', '헤지펀드',
    ],
    '부동산': [
        '아파트', '전세', '월세', '분양', '재건축', '청약', 'DSR', 'LTV',
        '대출', '주택', '오피스텔', '상가', '토지', '건설', '시세',
        '부동산', '임대', '매매', '경매', '리모델링',
    ],
    '연예': [
        '드라마', '영화', '아이돌', 'k-pop', '넷플릭스', '웹툰', '예능',
        '유튜브', 'netflix', '배우', '가수', '콘서트', '앨범', '시청률',
        'BTS', '블랙핑크', '뉴진스', '에스파', '음원', '스트리밍',
    ],
    '스포츠': [
        '축구', '야구', 'KBO', 'K리그', 'MLB', 'NBA', '손흥민',
        '올림픽', 'e스포츠', '프리미어리그', '챔피언스리그',
        '골프', '테니스', '격투기', 'UFC', 'F1',
        '국가대표', '월드컵', '아시안게임',
    ],
}


def _quick_classify(keyword: str) -> str:
    """Classify a topic keyword into a category using keyword matching."""
    kw_lower = f' {keyword.lower()} '
    best_cat = 'IT·테크'
    best_score = 0
    for cat, words in _CATEGORY_KEYWORDS.items():
        score = sum(1 for w in words if w in kw_lower)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


def _get_recent_category_counts(days: int = 7) -> Dict[str, int]:
    """Get category counts from recent articles to find underrepresented categories."""
    counts = {cat: 0 for cat in ALL_CATEGORIES}
    try:
        if SUPABASE_AVAILABLE and is_supabase_enabled():
            db = get_db_client()
            articles = db.list_articles(limit=50, published_only=True)
            for a in articles:
                cat = a.get('topic', 'TECH')
                if cat in counts:
                    counts[cat] += 1
            logger.info(f"Recent DB category counts: {dict(sorted(counts.items(), key=lambda x: x[1]))}")
    except Exception as e:
        logger.warning(f"Could not load recent categories: {e}")
    return counts


def _select_balanced_topics(topics: List[Dict], target_count: int) -> List[Dict]:
    """
    Select topics with category balance, prioritizing underrepresented categories.
    Checks DB for recent category distribution and picks from the least represented first.
    """
    # Classify all topics using Gemini AI
    try:
        from scripts.fetch_search_queries import classify_and_extract_keywords
        topics = classify_and_extract_keywords(topics)
        logger.info("Gemini AI classification complete")
    except Exception as e:
        logger.warning(f"Gemini classification failed, using keyword matching: {e}")
        for t in topics:
            t['_ai_category'] = _quick_classify(t.get('keyword', ''))
            t['_ai_core_keyword'] = ''

    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for t in topics:
        cat = t.get('_ai_category') or _quick_classify(t['keyword'])
        t['_quick_cat'] = cat
        buckets[cat].append(t)

    logger.info("Category distribution of trending topics:")
    for cat in ALL_CATEGORIES:
        logger.info(f"  {cat}: {len(buckets.get(cat, []))} topics")

    # Get recent category counts from DB → prioritize underrepresented
    recent_counts = _get_recent_category_counts()
    # Sort categories by count (ascending) → least represented first
    priority_order = sorted(ALL_CATEGORIES, key=lambda c: recent_counts.get(c, 0))
    logger.info(f"Category priority (least → most): {[f'{c}({recent_counts[c]})' for c in priority_order]}")

    selected = []
    used = set()

    # Priority round: pick from least represented categories first
    for cat in priority_order:
        for topic in buckets.get(cat, []):
            topic_id = id(topic)
            if topic_id not in used:
                selected.append(topic)
                used.add(topic_id)
                break  # one per category in priority round

    # Round-robin: fill more from each category
    max_per_cat = 3
    for round_idx in range(max_per_cat):
        for cat in priority_order:
            items = buckets.get(cat, [])
            if round_idx < len(items):
                topic = items[round_idx]
                topic_id = id(topic)
                if topic_id not in used:
                    selected.append(topic)
                    used.add(topic_id)

    # Fill remaining with highest-scoring unused topics
    for t in topics:
        if id(t) not in used:
            selected.append(t)
            used.add(id(t))

    # Category fallback pools — 각 카테고리별 보장 토픽
    import random as _rand
    today_str = datetime.now().strftime('%Y년 %m월')
    _CATEGORY_FALLBACKS = {
        '경제': [
            '코스피 코스닥 증시 전망 분석',
            '한국은행 기준금리 결정 경제 영향',
            '수출 무역수지 경기 전망',
            '삼성전자 실적 반도체 시장',
            '소비자물가 인플레이션 경제 전망',
            '국채 금리 채권시장 분석',
            '스타트업 투자 벤처캐피탈 동향',
            '고용 실업률 일자리 경제지표',
        ],
        '글로벌 경제': [
            '비트코인 암호화폐 시장 전망',
            '미국 연준 금리 결정 나스닥',
            '달러 환율 원달러 외환시장',
            '금값 원자재 국제 시세 동향',
            '유가 국제유가 에너지 시장',
            '미중 무역전쟁 관세 글로벌 공급망',
            '유럽 경제 ECB 금리 유로',
            '일본 엔화 일본은행 통화정책',
        ],
        'IT·테크': [
            'AI 인공지능 빅테크 최신 동향',
            '반도체 HBM 삼성전자 SK하이닉스 경쟁',
            '클라우드 AWS 구글 마이크로소프트',
            '스마트폰 갤럭시 아이폰 시장',
            '자율주행 전기차 테슬라 기술',
            '사이버보안 해킹 데이터 유출',
        ],
        '정치': [
            '국회 법안 처리 여야 합의',
            '대통령 정책 발표 국정운영',
            '총선 지방선거 여론조사',
            '외교 한미 한중 한일 관계',
            '국방 안보 군사 동향',
        ],
        '사회': [
            '교육 대입 수능 정책',
            '환경 기후변화 미세먼지',
            '인구 저출산 고령화 대책',
            '노동 최저임금 근로시간',
            '법원 대법원 판결 사건',
            '교통 안전 사고 예방',
        ],
        '글로벌 사회': [
            'UN 국제기구 결의 동향',
            '기후변화 탄소중립 국제 협약',
            '해외 자연재해 피해 복구',
            '이민 난민 국제 인권',
            '글로벌 보건 WHO 감염병',
        ],
        '부동산': [
            '서울 아파트 시세 매매 동향',
            '분양 청약 신규 단지 정보',
            '전세 월세 임대차 시장',
            '재건축 재개발 정비사업 전망',
            '부동산 대출 규제 DSR LTV',
            '공시가격 보유세 종부세',
        ],
        '연예': [
            'K-POP 아이돌 컴백 앨범 차트',
            '넷플릭스 드라마 OTT 화제작',
            '영화 박스오피스 흥행 분석',
            '예능 프로그램 시청률 화제',
            '아이돌 콘서트 투어 팬덤',
            '연예인 SNS 화제 이슈',
        ],
        '스포츠': [
            'KBO 프로야구 순위 경기 분석',
            'K리그 축구 경기 결과 분석',
            'MLB 메이저리그 한국 선수',
            'NBA 농구 시즌 분석',
            '손흥민 EPL 토트넘 경기',
            'WBC 월드베이스볼클래식 대한민국',
            '올림픽 국제대회 한국 선수단',
            'UFC 격투기 한국 선수',
        ],
    }

    # Guarantee at least 1 topic per category
    for cat in ALL_CATEGORIES:
        cat_bucket = buckets.get(cat, [])
        _rand.shuffle(cat_bucket)
        guaranteed = 0
        for t in cat_bucket:
            if id(t) not in used and guaranteed < 1:
                selected.insert(len(selected), t)
                used.add(id(t))
                guaranteed += 1
        # Fill with fallback if no trending topic found
        if guaranteed == 0 and cat in _CATEGORY_FALLBACKS:
            fallback_kw = _rand.choice(_CATEGORY_FALLBACKS[cat])
            fallback_topic = {
                'keyword': f'{fallback_kw} {today_str}',
                'source': 'category_guarantee',
                'score': 50,
                'region': 'KR',
                'url': '',
                '_quick_cat': cat,
            }
            selected.append(fallback_topic)
            used.add(id(fallback_topic))
            logger.info(f"  {cat} fallback guaranteed: {fallback_kw}")

    # Extra 경제 guarantee (always 2)
    eco_count = sum(1 for t in selected if t.get('_quick_cat') == '경제')
    while eco_count < 2:
        fallback_kw = _rand.choice(_CATEGORY_FALLBACKS['경제'])
        eco_topic = {
            'keyword': f'{fallback_kw} {today_str}',
            'source': 'economy_guarantee',
            'score': 50,
            'region': 'KR',
            'url': '',
            '_quick_cat': '경제',
        }
        selected.insert(0, eco_topic)
        used.add(id(eco_topic))
        eco_count += 1
        logger.info(f"경제 extra guarantee: {fallback_kw}")

    logger.info(f"Prepared {len(selected)} candidate topics (target: {target_count})")
    preview = ", ".join(f"[{t.get('_quick_cat', '?')}] {t.get('keyword', '')[:40]}" for t in selected[:5])
    logger.info(f"First 5 candidates: {preview}")
    return selected


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='AdSense Blog Automation System with Next.js',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and save 3 articles
  python main.py --articles 3

  # Generate without AdSense optimization
  python main.py --no-adsense --articles 2

  # Use specific markets
  python main.py --markets US UK --articles 2
        """
    )

    parser.add_argument(
        '--articles',
        type=int,
        default=1,
        help='Number of articles to generate (default: 1)'
    )

    parser.add_argument(
        '--markets',
        nargs='+',
        help='Target markets for trending topics (e.g., US UK CA)'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    parser.add_argument(
        '--no-adsense',
        action='store_true',
        help='Skip AdSense ad insertion'
    )

    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Skip Unsplash image fetching'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='../frontend/public/articles',
        help='Output directory for articles (default: ../frontend/public/articles)'
    )

    parser.add_argument(
        '--force-topic',
        type=str,
        default='',
        help='Force include this topic in the generation batch'
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("AdSense Blog Automation System (Next.js)")
    logger.info("=" * 80)
    logger.info(f"Articles to generate: {args.articles}")
    logger.info(f"Unsplash images: {not args.no_images}")
    logger.info(f"AdSense optimization: {not args.no_adsense}")
    logger.info(f"Output directory: {args.output}")
    logger.info("=" * 80)

    # Validate environment
    validate_environment()

    # Load configuration
    config = load_config(args.config)

    # Override markets if specified
    if args.markets:
        config['automation']['target_markets'] = args.markets

    # STEP 1: Fetch Trending Topics
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Fetching Trending Topics")
    logger.info("=" * 80)

    try:
        topics = get_all_trending_topics(
            markets=config['automation']['target_markets'],
            subreddits=config['automation'].get('subreddits', ['technology', 'worldnews']),
            limit_per_source=10
        )

        if not topics:
            logger.error("No trending topics found. Exiting.")
            sys.exit(1)

        # Force-include a specific topic if provided
        if args.force_topic:
            force = {
                'keyword': args.force_topic,
                'source': 'force_topic',
                'score': 999,
                'region': 'KR',
                'url': '',
                '_quick_cat': 'IT·테크',
            }
            topics.insert(0, force)
            logger.info(f"Force topic inserted: {args.force_topic}")

        logger.info(f"\nTop 10 trending topics:")
        for i, topic in enumerate(topics[:10], 1):
            logger.info(f"  {i}. {topic['keyword'][:60]}... (Source: {topic['source']}, Score: {topic['score']})")

    except Exception as e:
        logger.error(f"Error fetching trending topics: {e}")
        sys.exit(1)

    # STEP 1.5: Category-balanced topic selection
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1.5: Category-Balanced Topic Selection")
    logger.info("=" * 80)
    topics = _select_balanced_topics(topics, args.articles)

    # Filter out war/conflict topics (AdSense policy + editorial policy)
    _WAR_KEYWORDS = [
        'war', 'warfare', 'invasion', 'bombing', 'airstrike', 'missile strike',
        'death toll', 'genocide', 'massacre', 'casualties', 'armed conflict',
        'military attack', 'military offensive', 'ceasefire', 'occupation',
        '전쟁', '폭격', '공습', '미사일', '사망자', '학살', '침공', '교전', '포격',
    ]
    filtered_topics = []
    for t in topics:
        kw_lower = t.get('keyword', '').lower()
        if any(wk in kw_lower for wk in _WAR_KEYWORDS):
            logger.info(f"Excluding war-related topic: {t.get('keyword', '')[:60]}")
            continue
        filtered_topics.append(t)
    topics = filtered_topics

    # STEP 2: Generate Articles
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Generating Articles with Gemini")
    logger.info("=" * 80)

    try:
        articles = generate_multiple_articles(
            topics=topics,
            articles_count=args.articles,
            min_words=config['automation'].get('min_words', 1500),
            max_words=config['automation'].get('max_words', 2000)
        )

        if not articles:
            logger.error("No articles generated. Exiting.")
            sys.exit(1)

        logger.info(f"\nSuccessfully generated {len(articles)} articles:")
        for i, article in enumerate(articles, 1):
            cat = article.get('topic', '?')
            logger.info(f"  {i}. [{cat}] {article['title']} ({article['word_count']} words)")

    except Exception as e:
        logger.error(f"Error generating articles: {e}")
        sys.exit(1)

    # STEP 2.5: Verify & Correct Categories
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2.5: Verifying Article Categories with Gemini")
    logger.info("=" * 80)

    try:
        articles = classify_articles(articles)
        logger.info("✓ Category verification complete")
    except Exception as e:
        logger.warning(f"Category verification failed: {e}")
        logger.warning("Continuing with original categories...")

    # STEP 2.7: Validate External Links
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2.7: Validating External Links")
    logger.info("=" * 80)

    try:
        articles = validate_article_links(articles)
        logger.info("✓ External link validation complete")
    except Exception as e:
        logger.warning(f"Link validation failed: {e}")
        logger.warning("Continuing with unvalidated links...")

    # STEP 2.6: Fetch Unsplash Cover Images
    if not args.no_images:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2.6: Generating Cover Images (Gemini AI + Unsplash fallback)")
        logger.info("=" * 80)

        try:
            articles = fetch_images_for_articles(articles)
            images_found = sum(1 for a in articles if a.get('featured_image'))
            logger.info(f"✓ Images fetched: {images_found}/{len(articles)} articles have cover images")
        except Exception as e:
            logger.warning(f"Error fetching images: {e}")
            logger.warning("Continuing without cover images...")
    else:
        logger.info("\n⊘ Skipping image generation (--no-images flag)")

    # STEP 3: Optimize with AdSense
    if not args.no_adsense:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Optimizing AdSense Placement")
        logger.info("=" * 80)

        try:
            adsense_config = config.get('adsense', {})

            if validate_adsense_config(adsense_config):
                for i, article in enumerate(articles, 1):
                    logger.info(f"Optimizing article {i}/{len(articles)}: {article['title']}")

                    optimized_content = optimize_ad_placement(
                        article['content'],
                        adsense_config
                    )

                    article['content'] = optimized_content

                logger.info(f"✓ All articles optimized with AdSense ads")
            else:
                logger.warning("Invalid AdSense config. Skipping ad insertion.")

        except Exception as e:
            logger.error(f"Error optimizing AdSense: {e}")
            logger.warning("Continuing without ad optimization...")
    else:
        logger.info("\n⊘ Skipping AdSense optimization (--no-adsense flag)")

    # STEP 4: Save Articles
    logger.info("\n" + "=" * 80)
    if SUPABASE_AVAILABLE and is_supabase_enabled():
        logger.info("STEP 4: Saving Articles to Database and JSON")
    else:
        logger.info("STEP 4: Saving Articles to JSON")
    logger.info("=" * 80)

    try:
        results = save_multiple_articles(
            articles=articles,
            output_dir=args.output
        )

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SAVE SUMMARY")
        logger.info("=" * 80)

        success_count = sum(1 for r in results if r['success'])
        logger.info(f"Total articles: {len(results)}")
        logger.info(f"Successfully saved: {success_count}")
        logger.info(f"Failed: {len(results) - success_count}")

        logger.info("\nSaved articles:")
        for i, result in enumerate(results, 1):
            status_icon = "✓" if result['success'] else "✗"
            path = result['path'] if result['success'] else "Failed"
            logger.info(f"  {status_icon} {i}. {result['title']}")
            logger.info(f"     Slug: {result['slug']}")
            logger.info(f"     Path: {path}")

    except Exception as e:
        logger.error(f"Error saving articles: {e}")
        sys.exit(1)

    # STEP 5: Google Indexing Notification
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Google Indexing API Notification")
    logger.info("=" * 80)

    try:
        from scripts.notify_indexing import notify_urls

        saved_slugs = [r['slug'] for r in results if r['success']]
        if saved_slugs:
            article_urls = [
                f"https://www.nexustopic.com/article/{slug}"
                for slug in saved_slugs
            ]
            logger.info(f"Notifying Google about {len(article_urls)} new article(s)...")
            idx_result = notify_urls(article_urls)
            logger.info(
                f"✓ Indexing notification complete: "
                f"{idx_result['success']} succeeded, {idx_result['failed']} failed"
            )
        else:
            logger.info("No successfully saved articles to notify.")
    except Exception as e:
        logger.warning(f"Google Indexing notification failed: {e}")
        logger.warning("Continuing without indexing notification...")

    # Final Summary
    logger.info("\n" + "=" * 80)
    logger.info("AUTOMATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Articles saved to: {args.output}")
    logger.info("Next steps:")
    logger.info("  1. cd frontend")
    logger.info("  2. npm run dev")
    logger.info("  3. Open http://localhost:3000")
    logger.info("\nTo deploy:")
    logger.info("  1. git add .")
    logger.info("  2. git commit -m 'Add articles'")
    logger.info("  3. git push")
    logger.info("  4. Vercel will auto-deploy")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\nProcess interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
