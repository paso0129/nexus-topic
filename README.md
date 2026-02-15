# NexusTopic Backend - AI Content Generation Automation

트렌딩 토픽을 자동 수집하고 Gemini AI로 SEO 최적화된 뉴스 기사를 생성하는 백엔드입니다.

## 관련 프로젝트

- **Frontend**: [nexus-topic-frontend](https://github.com/paso0129/nexus-topic-frontend) (Next.js 14)
- **Live Site**: [www.nexustopic.com](https://www.nexustopic.com)

## 아키텍처

```
트렌딩 수집 (HackerNews + Google Trends)
    ↓
Gemini AI 기사 생성 (CLI: 2.5 Pro / API: 3 Flash Preview)
    ↓
커버 이미지 생성 (Gemini 2.5 Flash Image → Unsplash 폴백)
    ↓
Supabase 저장 (DB + Storage)
    ↓
프론트엔드 캐시 Revalidation
```

## 기술 스택

- **Python**: 3.11
- **AI**: Gemini 2.5 Pro (CLI) / Gemini 3 Flash Preview (API fallback)
- **이미지**: Gemini 2.5 Flash Image → Unsplash fallback
- **DB**: Supabase (PostgreSQL + Storage)
- **CI/CD**: GitHub Actions (매일 2회 자동 실행)
- **호스팅**: Vercel (Frontend) + Cloudflare (DNS)

## 주요 기능

- 트렌딩 토픽 자동 수집 (Google Trends, HackerNews)
- Gemini AI 콘텐츠 생성 (1500-2000단어)
- AI 커버 이미지 생성 (Gemini Nano Banana) + Supabase Storage 업로드
- 외부 링크 자동 삽입 (Wikipedia, Reuters, 공식 사이트 등 4-6개)
- 내부 링크는 최소한으로 (0-1개, 직접 관련된 경우만)
- SEO 자동 최적화
- 중복 기사 방지 (키워드 유사도 + LLM 시맨틱 체크)
- 기사 생성 후 프론트엔드 자동 revalidation

## 서비스 콘솔

| 서비스 | URL |
|--------|-----|
| GCP Billing | https://console.cloud.google.com/billing/013CFE-C30B16-32CF70?authuser=1&project=nexus-487502 |
| Supabase | https://supabase.com/dashboard |
| Vercel | https://vercel.com/dashboard |
| Cloudflare | https://dash.cloudflare.com/ |
| GitHub Actions | https://github.com/paso0129/nexus-topic/actions |

## 환경 변수 (GitHub Secrets)

| 변수명 | 용도 |
|--------|------|
| `GOOGLE_API_KEY` | Gemini API (기사 생성 + 이미지 생성) |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_KEY` | Supabase Service Role Key |
| `UNSPLASH_ACCESS_KEY` | Unsplash API (이미지 폴백) |
| `REVALIDATION_SECRET` | 프론트엔드 캐시 revalidation 토큰 |

## 빠른 시작

```bash
# 클론
git clone https://github.com/paso0129/nexus-topic.git
cd nexus-topic/backend

# 의존성 설치
pip install -r requirements.txt

# .env 설정
cp ../.env.example .env
# GOOGLE_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY 등 입력

# 기사 생성 (1개)
python main.py --articles 1
```

## 프로젝트 구조

```
backend/
├── scripts/
│   ├── fetch_trending.py      # 트렌드 수집 (HackerNews + Google Trends)
│   ├── generate_content.py    # Gemini AI 기사 생성
│   ├── fetch_images.py        # 커버 이미지 (Gemini AI + Unsplash)
│   ├── optimize_adsense.py    # AdSense 최적화
│   ├── save_article.py        # Supabase DB 저장
│   └── database.py            # DB 클라이언트
├── main.py                    # 메인 실행 파일
├── config.yaml                # 설정
└── requirements.txt           # Python 의존성
```

## GitHub Actions 자동화

매일 2회 자동 실행 (UTC 01:00, 13:00 = KST 10:00, 22:00):

1. 트렌딩 토픽 수집
2. 기사 생성 (기본 3개)
3. AI 커버 이미지 생성 + Supabase 업로드
4. Supabase DB 저장
5. 프론트엔드 캐시 revalidation

수동 실행: Actions → Generate Daily Articles → Run workflow

## 기사 생성 규칙

- **외부 링크 우선**: 기사당 4-6개 외부 링크 삽입 (Wikipedia, 공식 사이트, 주요 뉴스 매체 등)
- **내부 링크 최소화**: 직접 관련된 경우에만 0-1개
- **카테고리**: AI, BIZ & IT, CARS, CULTURE, GAMING, HEALTH, POLICY, SCIENCE, SECURITY, SPACE, TECH
- **분량**: 1500-2000 단어
- **이미지**: Gemini AI 생성 우선, 실패 시 Unsplash

## 비용

- **Gemini API**: GCP $300 무료 크레딧 사용 중 (90일 기한)
  - 기사 생성: gemini-3-flash-preview (무료 티어)
  - 이미지 생성: gemini-2.5-flash-image (~$0.039/장)
- **Supabase**: Free tier
- **Vercel**: Free tier
- **Cloudflare**: Free tier
- **Unsplash**: Free tier (이미지 폴백)
