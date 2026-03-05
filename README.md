# NexusTopic Backend — AI Content Generation Pipeline

트렌딩 토픽을 자동 수집하고, 저자 페르소나 기반 Gemini AI로 사람이 쓴 것 같은 분석 기사를 생성하는 파이프라인입니다.

## 관련 프로젝트

- **Frontend**: [nexus-topic-frontend](https://github.com/paso0129/nexus-topic-frontend) (Next.js 14)
- **Live Site**: [www.nexustopic.com](https://www.nexustopic.com)

## 아키텍처

```
트렌딩 수집 (Google Trends + Reddit 18개 서브레딧)
    ↓
실제 검색 데이터 수집 (Google Autocomplete + pytrends)
    ↓
카테고리별 라운드로빈 주제 선택 (9개 카테고리 균형, ECONOMY 우선)
    ↓
저자 페르소나 매칭 (Alex Chen / Sarah Mitchell / Maya Rodriguez)
    ↓
Gemini AI 기사 생성 (CLI: 3.1 Pro Preview / API: 2.5 Pro 폴백)
  - Anti-AI 패턴 + 날짜 기반 팩트체크 프롬프팅
    ↓
Gemini AI 카테고리 재분류 검증
    ↓
커버 이미지 생성 (Gemini 2.5 Flash Image → Unsplash 폴백)
    ↓
Supabase 저장 (DB + Storage)
    ↓
Google Indexing API + IndexNow + WebSub 알림
    ↓
프론트엔드 ISR 캐시 Revalidation
```

## 기술 스택

| 항목 | 기술 |
|------|------|
| **언어** | Python 3.10+ |
| **AI 기사** | Gemini 3.1 Pro Preview (CLI, 1차) → Gemini 2.5 Pro (API, 폴백) |
| **AI 이미지** | Gemini 2.5 Flash Image → Unsplash (폴백) |
| **AI 분류** | Gemini AI 기반 (키워드 매칭 → AI 분류로 전환) |
| **DB** | Supabase (PostgreSQL + Storage) |
| **SEO** | Google Indexing API + IndexNow + WebSub + Search Console Analytics |
| **CI/CD** | GitHub Actions (하루 4회 자동 생성) |
| **호스팅** | Vercel (Frontend) + Cloudflare (DNS) |

## 카테고리 (9개)

IT & BIZ, CULTURE, ECONOMY, ENTERTAINMENT, GAMING, HEALTH, POLICY, SCIENCE, TECH

> SECURITY 카테고리 제거 (2026-03), ECONOMY 2개 기사 우선 보장

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
│   ├── fetch_trending.py          # 트렌딩 수집 (Google Trends + Reddit)
│   ├── fetch_search_queries.py    # 실제 검색 데이터 수집 (Autocomplete + pytrends)
│   ├── generate_content.py        # Gemini 기사 생성 + 저자 페르소나 + 팩트체크
│   ├── reclassify.py              # Gemini AI 카테고리 재분류
│   ├── fetch_images.py            # 커버 이미지 (Gemini AI + Unsplash)
│   ├── backfill_images.py         # 이미지 없는 기사 보충
│   ├── optimize_adsense.py        # AdSense 배치 최적화
│   ├── save_article.py            # Supabase + JSON 이중 저장
│   ├── notify_indexing.py         # Google Indexing API (URL_UPDATED / URL_DELETED)
│   ├── notify_search_engines.py   # IndexNow + WebSub 알림
│   ├── batch_index.py             # 일괄 인덱싱 (최근 24시간 + 정적 페이지)
│   ├── submit_sitemaps.py         # Search Console 사이트맵 제출
│   ├── search_analytics.py        # Search Console 성과 분석
│   ├── cleanup_deleted.py         # 삭제된 기사 URL_DELETED 전송
│   └── supabase_schema.sql        # DB 스키마
└── .github/workflows/
    ├── generate-content.yml       # 자동 기사 생성 (하루 4회, 랜덤 딜레이)
    ├── backfill-images.yml        # 이미지 없는 기사 AI 이미지 보충
    ├── expand-articles.yml        # 1500단어 미만 기사 보강
    ├── cleanup-deleted.yml        # 삭제 기사 인덱싱 정리
    ├── delete-urls.yml            # URL 삭제 요청
    ├── search-analytics.yml       # Search Console 성과 수집
    ├── reindex-all.yml            # 전체 URL 일괄 인덱싱
    └── fix-article.yml            # 기사 내용 수정 (일회성)
```

## 실행 방법

> **로컬 실행 불가** — .env 파일이 없으며 모든 시크릿은 GitHub Actions Secrets에서 관리됩니다.

```bash
# GitHub Actions에서 수동 실행 (workflow_dispatch)
gh workflow run "Generate Daily Articles" --repo paso0129/nexus-topic -f articles=1
```

## GitHub Actions Workflows

| Workflow | 트리거 | 설명 |
|----------|--------|------|
| `generate-content.yml` | 하루 4회 cron + 수동 | 기사 자동 생성 (1개/회, 랜덤 5~55분 딜레이) |
| `backfill-images.yml` | 수동 | 이미지 없는 기사에 Gemini AI/Unsplash 이미지 보충 |
| `expand-articles.yml` | 수동 | 1500단어 미만 기사 보강 |
| `cleanup-deleted.yml` | 수동 | 삭제된 기사 URL_DELETED 전송 |
| `delete-urls.yml` | 수동 | 특정 URL 삭제 요청 |
| `search-analytics.yml` | 수동 | Search Console 성과 데이터 수집 |
| `reindex-all.yml` | 수동 | 전체 URL 일괄 Google Indexing |
| `fix-article.yml` | 수동 | 기사 내용 일회성 수정 |

## 환경 변수 (GitHub Secrets)

| 변수명 | 용도 |
|--------|------|
| `GOOGLE_API_KEY` | Gemini API (기사 생성 + 이미지 생성) |
| `GOOGLE_INDEXING_SA_KEY` | Google Indexing API 서비스 계정 JSON |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_KEY` | Supabase Service Role Key |
| `UNSPLASH_ACCESS_KEY` | Unsplash API (이미지 폴백) |
| `REVALIDATION_SECRET` | 프론트엔드 캐시 revalidation 토큰 |

## 트렌딩 소스 & 필터

**소스 (2개):**
- Google Trends — US/UK/CA 마켓 일일 트렌딩 RSS
- Reddit — 9개 카테고리, 18개 서브레딧 (technology, economics, gaming, politics 등)

**필터:**
- 전쟁/폭력 콘텐츠 필터 (AdSense 정책 준수)
- 경제 키워드 예외 — `kospi`, `stock`, `market`, `crash` 등이 포함된 경우 전쟁 필터 우회
- HIGH CPC 부스트 — 금융/보험/법률/헬스/AI/부동산/에너지 키워드 점수 상향
- 중복 제거 — Jaccard 유사도 0.5 이상 필터링

## 주요 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-03-05 | 트렌딩 소스 단순화: 7개 → Google Trends + Reddit 2개 (카테고리 균형) |
| 2026-03-05 | 날짜 기반 팩트체크 프롬프팅 추가 (가격/통계 hallucination 방지) |
| 2026-03-05 | 전쟁 필터 경제 키워드 예외 처리 (KOSPI 폭락 등 경제 기사 허용) |
| 2026-03-03 | 실제 검색 데이터 수집 (Google Autocomplete + pytrends) → 프롬프트 주입 |
| 2026-03-03 | Gemini AI 기반 카테고리 분류로 전환 (키워드 매칭 제거) |
| 2026-03-03 | SECURITY 카테고리 제거, ECONOMY 2개 기사 우선 보장 |
| 2026-03-03 | 기사 확장 스크립트 추가 (1500단어 미만 자동 보강) |
| 2026-03-01 | 기사 구조 다양화 (5가지 랜덤 템플릿) |
| 2026-02-28 | SEO 파이프라인 개선: 검색 수요 필터, 전쟁 필터, 프롬프트 튜닝 |
| 2026-02-25 | Gemini 3.1 Pro Preview (CLI 1차) → 2.5 Pro (API 폴백) 체계 확립 |
| 2026-02-24 | 카테고리 균형 로직: 과소 대표 카테고리 우선 |
| 2026-02-22 | 기사 생성 스케줄 하루 4회 재개 (랜덤 5~55분 딜레이) |
| 2026-02-21 | RSS 소스 확장: Bloomberg, CNBC, Google News, Yahoo Finance 등 |
| 2026-02-21 | Search Console 분석 스크립트 + 워크플로우 추가 |
| 2026-02-19 | AI + BIZ & IT → IT & BIZ 카테고리 통합 |
| 2026-02-19 | 저자 페르소나 시스템 추가 (성별/연령대 기반 글쓰기 톤) |
| 2026-02-19 | Anti-AI 프롬프트 전면 개편 (사람이 쓴 것 같은 글) |
| 2026-02-19 | 기사 352개 → 31개로 축소 (품질 중심 전환) |
| 2026-02-19 | Google Indexing API URL_DELETED 지원 추가 |
| 2026-02-17 | Google Indexing API 자동 알림 추가 |
| 2026-02-15 | Gemini AI 이미지 생성 + Supabase Storage 업로드 |
| 2026-02-12 | AdSense 승인 요청 제출 |
