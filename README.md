# NexusTopic Backend — AI Content Generation Pipeline

트렌딩 토픽을 자동 수집하고, 저자 페르소나 기반 Gemini AI로 사람이 쓴 것 같은 분석 기사를 생성하는 파이프라인입니다.

## 관련 프로젝트

- **Frontend**: [nexus-topic-frontend](https://github.com/paso0129/nexus-topic-frontend) (Next.js 14)
- **Live Site**: [www.nexustopic.com](https://www.nexustopic.com)

## 아키텍처

```
트렌딩 수집 (Google Trends + Reddit + HackerNews + Dev.to + ProductHunt + RSS)
    ↓
카테고리별 라운드로빈 주제 선택 (10개 카테고리 균형)
    ↓
저자 페르소나 매칭 (Alex Chen / Sarah Mitchell / Maya Rodriguez)
    ↓
Gemini AI 기사 생성 (CLI: 2.5 Pro / API: 3 Flash Preview)
  - Anti-AI 패턴 적용 (구어체, 1인칭, 비유, 미래 예측)
    ↓
AI 카테고리 재분류 검증
    ↓
커버 이미지 생성 (Gemini 2.5 Flash Image → Unsplash 폴백)
    ↓
Supabase 저장 (DB + Storage)
    ↓
Google Indexing API 알림
    ↓
프론트엔드 ISR 캐시 Revalidation
```

## 기술 스택

| 항목 | 기술 |
|------|------|
| **언어** | Python 3.10+ |
| **AI 기사** | Gemini 2.5 Pro (CLI, 1차) → Gemini 3 Flash Preview (API, 폴백) |
| **AI 이미지** | Gemini 2.5 Flash Image → Unsplash (폴백) |
| **AI 분류** | Gemini 3 Flash Preview (API) → Gemini 2.5 Flash (CLI, 폴백) |
| **DB** | Supabase (PostgreSQL + Storage) |
| **SEO** | Google Indexing API (자동 알림) |
| **CI/CD** | GitHub Actions |
| **호스팅** | Vercel (Frontend) + Cloudflare (DNS) |

## 카테고리 (10개)

IT & BIZ, CULTURE, ECONOMY, ENTERTAINMENT, GAMING, HEALTH, POLICY, SCIENCE, SECURITY, TECH

> AI + BIZ & IT 카테고리가 2026-02-19에 IT & BIZ로 통합됨

## 저자 시스템

각 기사는 카테고리에 따라 저자가 자동 매칭되며, 저자별 성별/연령대/글쓰기 톤이 프롬프트에 반영됩니다:

| 저자 | 성별/나이 | 담당 카테고리 | 톤 |
|------|-----------|--------------|-----|
| Alex Chen | 남/35 | IT & BIZ, TECH, SECURITY, SCIENCE | 직설적, 드라이 유머, 회의적이지만 진짜에 흥분 |
| Sarah Mitchell | 여/38 | POLICY, ECONOMY, HEALTH | 정밀하고 날카로움, PR 뒤의 숫자를 찾음 |
| Maya Rodriguez | 여/32 | CULTURE, GAMING, ENTERTAINMENT | 따뜻하고 위트 있음, 커뮤니티 내부자 시점 |

## Anti-AI 글쓰기 규칙

프롬프트에 다음이 적용되어 구글 AI 탐지를 회피합니다:

- AI 클리셰 금지 ("In a move that...", "It remains to be seen", "landscape", "paradigm shift" 등)
- 문장 길이 극적 변화 (짧은 5-8단어 + 긴 분석 문장)
- 1인칭 자연스러운 사용 ("What strikes me...", "I keep coming back to...")
- 비교/선례 분석 필수 ("Compared to method A, this new approach B...")
- 미래 영향 예측 필수 (구체적 산업/기간/변화 명시)
- 각 기사마다 다른 의견 형식 (blockquote, 인라인, 괄호, 볼드 등)

## 프로젝트 구조

```
backend/
├── main.py                        # CLI 엔트리포인트 (파이프라인 실행)
├── config.yaml                    # 설정
├── requirements.txt
├── scripts/
│   ├── database.py                # Supabase 클라이언트
│   ├── fetch_trending.py          # 트렌딩 수집 (6개 소스)
│   ├── generate_content.py        # Gemini 기사 생성 + 저자 페르소나
│   ├── reclassify.py              # AI 카테고리 재분류
│   ├── fetch_images.py            # 커버 이미지 (Gemini AI + Unsplash)
│   ├── optimize_adsense.py        # AdSense 배치 최적화
│   ├── save_article.py            # Supabase + JSON 이중 저장
│   ├── notify_indexing.py         # Google Indexing API (URL_UPDATED / URL_DELETED)
│   ├── batch_index.py             # 일괄 인덱싱 (정적 페이지 + 카테고리 포함)
│   ├── rewrite_articles.py        # 기존 기사 일괄 리라이팅
│   └── supabase_schema.sql        # DB 스키마
└── .github/workflows/
    ├── generate-content.yml       # 자동 기사 생성 (현재 일시 중단)
    ├── reindex.yml                # 수동 Google Indexing API 호출
    └── backfill-images.yml        # 이미지 없는 기사 보충
```

## 실행 방법

```bash
cd backend
source venv/bin/activate

# 기사 생성
python main.py --articles 2

# 기존 기사 리라이팅 (저자 페르소나 적용)
python scripts/rewrite_articles.py --limit 10

# Google Indexing API 일괄 호출 (GitHub Actions 권장)
python -m scripts.batch_index
```

## GitHub Actions Workflows

| Workflow | 트리거 | 설명 |
|----------|--------|------|
| `generate-content.yml` | ~~12시간마다~~ 일시 중단 (수동만) | 기사 자동 생성 (2개/회) |
| `reindex.yml` | 수동 (workflow_dispatch) | 전체 URL Google Indexing API 알림 |
| `backfill-images.yml` | 수동 | 이미지 없는 기사에 AI 이미지 생성 |

> 자동 포스팅은 콘텐츠 품질 개선 기간 동안 일시 중단됨 (2026-02-19~)

## 환경 변수 (GitHub Secrets)

| 변수명 | 용도 |
|--------|------|
| `GOOGLE_API_KEY` | Gemini API (기사 생성 + 이미지 생성) |
| `GOOGLE_INDEXING_SA_KEY` | Google Indexing API 서비스 계정 JSON |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_KEY` | Supabase Service Role Key |
| `UNSPLASH_ACCESS_KEY` | Unsplash API (이미지 폴백) |
| `NEWSAPI_KEY` | NewsAPI (트렌딩 수집) |
| `REVALIDATION_SECRET` | 프론트엔드 캐시 revalidation 토큰 |

## 주요 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-02-19 | AI + BIZ & IT → IT & BIZ 카테고리 통합 |
| 2026-02-19 | 저자 페르소나 시스템 추가 (성별/연령대 기반 글쓰기 톤) |
| 2026-02-19 | Anti-AI 프롬프트 전면 개편 (사람이 쓴 것 같은 글) |
| 2026-02-19 | 게시 빈도 축소 (4시간/11개 → 12시간/2개) → 일시 중단 |
| 2026-02-19 | 기사 352개 → 31개로 축소 (품질 중심 전환) |
| 2026-02-19 | 기존 기사 전량 리라이팅 (사람냄새 전환) |
| 2026-02-19 | Google Indexing API URL_DELETED 지원 추가 |
| 2026-02-19 | reindex.yml workflow 추가 (수동 일괄 인덱싱) |
| 2026-02-17 | Google Indexing API 자동 알림 추가 |
| 2026-02-15 | Gemini AI 이미지 생성 + Supabase Storage 업로드 |
| 2026-02-12 | AdSense 승인 요청 제출 |
