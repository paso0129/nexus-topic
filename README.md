# NexusTopic Backend - AI Content Generation Automation

Python 기반의 자동화된 블로그 콘텐츠 생성 백엔드입니다. Claude AI를 사용하여 트렌딩 토픽을 수집하고 SEO 최적화된 콘텐츠를 생성합니다.

## 🔗 관련 프로젝트

- **Frontend**: [nexus-topic-frontend](https://github.com/paso0129/nexus-topic-frontend) (Next.js 14)
- **Live Site**: [nexustopic.com](https://nexustopic.com)

## 🌟 주요 기능

- 🔥 트렌딩 토픽 자동 수집 (Google Trends, Reddit, HackerNews)
- 🤖 Claude AI 콘텐츠 생성 (1500-2000단어)
- 📊 SEO 자동 최적화
- 💵 AdSense 전략적 배치
- 📄 JSON 기반 데이터 저장

## 📋 기술 스택

- **Python**: 3.8+
- **AI**: Anthropic Claude (claude-sonnet-4-5)
- **Libraries**: PyTrends, PRAW (Reddit), BeautifulSoup4
- **Output**: JSON 파일 (Frontend에서 사용)

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/paso0129/nexus-topic.git
cd nexus-topic
```

### 2. 가상 환경 설정

```bash
cd backend

# 가상 환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
cp ../.env.example .env
# .env 파일 편집하여 API 키 입력
```

필수 환경 변수:
```env
ANTHROPIC_API_KEY=your_api_key_here
```

선택적 환경 변수:
```env
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_app_name
```

### 4. 콘텐츠 생성

```bash
python main.py --articles 3
```

생성된 JSON 파일은 `../frontend/public/articles/` 디렉토리에 저장됩니다.

## 🔑 필요한 API 키

### Anthropic Claude API (필수)
1. [Anthropic Console](https://console.anthropic.com/) 방문
2. API Key 생성
3. `.env` 파일의 `ANTHROPIC_API_KEY`에 추가

### Reddit API (선택사항)
1. [Reddit Apps](https://www.reddit.com/prefs/apps) 방문
2. Script 앱 생성
3. Client ID와 Secret을 `.env`에 추가

**참고**: Reddit API는 선택사항입니다. Reddit 없이도 Google Trends와 HackerNews로 충분한 콘텐츠를 생성할 수 있습니다.

## 📦 프로젝트 구조

```
backend/
├── scripts/
│   ├── fetch_trending.py      # 트렌드 수집
│   ├── generate_content.py    # AI 콘텐츠 생성
│   ├── optimize_adsense.py    # AdSense 최적화
│   └── save_article.py        # JSON 저장
├── main.py                    # 메인 실행 파일
├── config.yaml               # 설정
└── requirements.txt          # Python 의존성
```

## 🔧 설정 커스터마이징

### config.yaml

```yaml
automation:
  content_model: "claude-sonnet-4-5-20250929"
  min_words: 1500
  max_words: 2000
  target_audience: "North American and European readers"

adsense:
  placements_per_article: 12
  min_spacing_paragraphs: 3
```

## 📝 사용 예시

### 기본 사용
```bash
python main.py --articles 3
```

### 특정 소스에서만 수집
```python
# main.py에서 소스 선택
topics = fetch_trending_topics(
    sources=['hackernews', 'google_trends']  # Reddit 제외
)
```

## 🔄 워크플로우

1. **트렌드 수집** (`fetch_trending.py`)
   - Google Trends: 인기 검색어
   - HackerNews: 상위 포스트
   - Reddit: Hot 포스트 (선택사항)

2. **콘텐츠 생성** (`generate_content.py`)
   - Claude AI로 1500-2000단어 아티클 생성
   - SEO 최적화 (메타 태그, 키워드)
   - HTML 마크업 생성

3. **AdSense 최적화** (`optimize_adsense.py`)
   - 전략적 광고 위치 계산
   - 12개 광고 단위 배치
   - 가독성 유지

4. **JSON 저장** (`save_article.py`)
   - 개별 아티클 JSON 파일
   - 인덱스 파일 업데이트
   - Frontend에서 바로 사용 가능

## 🌐 Frontend 연동

생성된 JSON 파일은 Frontend 레포의 `public/articles/` 디렉토리로 복사해야 합니다:

```bash
# Backend에서 아티클 생성
python main.py --articles 3

# Frontend 레포로 복사 (Frontend 레포를 별도로 클론한 경우)
cp -r ../frontend/public/articles/*.json /path/to/nexus-topic-frontend/public/articles/

# Frontend 레포에서 커밋 & 푸시
cd /path/to/nexus-topic-frontend
git add public/articles/*.json
git commit -m "Add new articles"
git push
```

Vercel이 자동으로 재배포합니다.

## 🤖 자동화 (선택사항)

### GitHub Actions

`.github/workflows/generate-content.yml`:

```yaml
name: Generate Content

on:
  schedule:
    - cron: '0 10 * * *'  # 매일 오전 10시
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt

      - name: Generate articles
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          cd backend
          python main.py --articles 2

      - name: Commit articles
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add frontend/public/articles/
          git commit -m "Auto-generate articles [skip ci]" || exit 0
          git push
```

## 🐛 문제 해결

### Claude API 에러
```bash
# 모델 이름 확인
# config.yaml에서 "claude-sonnet-4-5-20250929" 사용
```

### JSON 파일이 생성되지 않음
```bash
# 출력 디렉토리 확인
ls -la ../frontend/public/articles/

# 권한 문제 확인
chmod +w ../frontend/public/articles/
```

### 트렌드 수집 실패
- Google Trends: API 제한 확인 (10-20초 대기)
- Reddit: API 키 확인 또는 Reddit 제외하고 진행
- HackerNews: 네트워크 연결 확인

## 📊 콘텐츠 품질

### SEO 최적화
- 1500-2000단어 (검색엔진 선호)
- 키워드 밀도 2-3%
- 헤딩 구조 (H2, H3)
- 메타 디스크립션 자동 생성

### 가독성
- 짧은 문단 (3-4문장)
- 불릿 포인트 사용
- 명확한 소제목
- 예시와 설명 포함

## 📝 라이선스

MIT License - 상업적 사용 가능

## ⚠️ 주의사항

- Anthropic API 사용량 모니터링 필수
- 생성된 콘텐츠는 검토 권장
- Google AdSense 정책 준수
- 백업 정기적으로 실행

## 🤝 기여

이슈와 PR 환영합니다!

---

**Powered by Claude AI** 🤖

트렌딩 토픽을 놓치지 마세요!
