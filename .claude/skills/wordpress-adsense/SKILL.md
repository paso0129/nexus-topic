# WordPress AdSense Automation Skill

## Description
Automated WordPress blog publishing system with Google AdSense monetization. Discovers trending topics, generates SEO-optimized content using Claude AI, and publishes with strategic ad placement.

## Capabilities

### 1. Trending Topic Discovery
- **Google Trends**: Monitor trending searches in target markets (US, UK, CA, DE, FR)
- **Reddit**: Track hot topics from technology and news subreddits
- **HackerNews**: Fetch top stories from tech community
- Returns scored and ranked topics with regional data

### 2. AI Content Generation
- **Claude API Integration**: Generate high-quality articles (1500-2000 words)
- **SEO Optimization**: Auto-generate meta descriptions, keywords, and titles
- **HTML Formatting**: Proper heading structure, paragraphs, and readability
- **Reading Time**: Calculate and include estimated reading time

### 3. AdSense Optimization
- **Strategic Placement**: Insert ads at optimal positions
  - After introduction (captures immediate attention)
  - Mid-content (during engagement)
  - Before conclusion (exit intent)
- **Responsive Units**: Mobile and desktop optimized ad codes
- **Content-Ad Balance**: Maintain user experience while maximizing revenue

### 4. WordPress Publishing
- **REST API**: Secure authentication with application passwords
- **Automated Publishing**: Create posts with proper metadata
- **Category/Tag Management**: Auto-assign relevant taxonomies
- **Featured Images**: Optional image support
- **Status Management**: Draft, pending, or publish states

## Configuration

### Required Environment Variables
```
WP_USERNAME=your_wordpress_username
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
REDDIT_CLIENT_ID=xxxxx
REDDIT_CLIENT_SECRET=xxxxx
ADSENSE_CLIENT_ID=ca-pub-xxxxx
```

### Config File (config.yaml)
```yaml
wordpress:
  url: "https://yourblog.com"

adsense:
  client_id: "ca-pub-XXXXXXXXXXXXXXXX"
  slots:
    header: "1234567890"
    in_article: "0987654321"
    sidebar: "1122334455"

automation:
  target_markets: ["US", "UK", "CA", "DE", "FR"]
  articles_per_run: 3
  min_words: 1500
  max_words: 2000
```

## Usage

### Command Line
```bash
# Generate and publish articles
python main.py --articles 3

# Dry run (no publishing)
python main.py --dry-run

# Specific market
python main.py --market US --articles 1
```

### Programmatic
```python
from scripts.fetch_trending import fetch_google_trends, fetch_reddit_trending
from scripts.generate_content import generate_article
from scripts.optimize_adsense import optimize_ad_placement
from scripts.publish_wordpress import publish_to_wordpress

# Fetch trending topics
topics = fetch_google_trends(markets=['US', 'UK'])

# Generate content
article = generate_article(topics[0]['keyword'])

# Optimize with ads
optimized_html = optimize_ad_placement(
    article['content'],
    adsense_config
)

# Publish
result = publish_to_wordpress(article, wp_config)
```

## Revenue Optimization Tips

1. **Content Quality**: Higher quality = longer engagement = more ad views
2. **Topic Selection**: Focus on trending, high-CPC keywords
3. **Ad Placement**: Test different positions and monitor CTR
4. **Mobile First**: Ensure responsive design for mobile traffic
5. **Update Frequency**: Regular publishing improves SEO rankings

## Security Considerations

- Use WordPress Application Passwords (not main password)
- Store API keys in environment variables (never commit to git)
- Use HTTPS for all API communications
- Implement rate limiting to avoid API quotas
- Regular security updates for dependencies

## Monitoring & Analytics

- Track published post URLs
- Monitor AdSense revenue per article
- Analyze traffic sources and keywords
- A/B test ad placements
- Review content performance monthly

## Troubleshooting

### WordPress Connection Issues
- Verify Application Password is correct
- Check WordPress REST API is enabled
- Ensure HTTPS connection
- Verify user has publishing permissions

### AdSense Not Showing
- Confirm AdSense account is approved
- Check ad codes are correct
- Verify site is added to AdSense account
- Allow 24-48 hours for new ads to activate

### Content Generation Errors
- Check Anthropic API key and quota
- Verify Claude API is accessible
- Review prompt format and parameters
- Check network connectivity

## Best Practices

1. **Start Small**: Test with 1-2 articles before automating
2. **Review Content**: Human review before publishing (at least initially)
3. **Monitor Quality**: Regular checks to ensure content meets standards
4. **AdSense Compliance**: Follow Google's policies strictly
5. **Backup**: Keep backups of published content
6. **Logging**: Enable detailed logging for debugging

## Future Enhancements

- Image generation and optimization
- Multi-language support
- Social media auto-sharing
- Email newsletter integration
- Performance analytics dashboard
- A/B testing framework for ads
