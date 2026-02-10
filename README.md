# AdSense Blog - AI-Powered Content Platform

Next.js 기반의 완전 자동화된 블로그 플랫폼으로 Google AdSense 수익 최적화를 지원합니다. Claude AI로 SEO 최적화된 콘텐츠를 생성하고 Vercel에 자동 배포됩니다.

## 🌟 주요 기능

### Frontend (Next.js 14)
- ⚡ App Router + Server Components
- 🎨 Tailwind CSS + 다크모드
- 📱 완전 반응형 디자인
- 🚀 정적 생성 (SSG) + ISR
- 💰 AdSense 최적화 배치
- 🔍 SEO 최적화 (메타태그, Open Graph, Twitter Cards)

### Backend (Python)
- 🔥 트렌딩 토픽 자동 수집 (Google Trends, Reddit, HackerNews)
- 🤖 Claude AI 콘텐츠 생성 (1500-2000단어)
- 📊 SEO 자동 최적화
- 💵 AdSense 전략적 배치
- 📄 JSON 기반 데이터 저장

## 📋 기술 스택

- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS
- **Backend**: Python 3.8+, Claude AI, PyTrends, PRAW
- **Deployment**: Vercel (프론트엔드), GitHub Actions (자동화)
- **DNS**: Cloudflare (도메인 관리)

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone <your-repo>
cd wordpress-adsense-automation
```

### 2. Backend 설정

```bash
cd backend

# 가상 환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp ../.env.example .env
# .env 파일 편집하여 API 키 입력
```

### 3. Frontend 설정

```bash
cd ../frontend

# 의존성 설치
npm install

# 환경 변수 설정
cp .env.local.example .env.local
# .env.local 파일 편집
```

### 4. 콘텐츠 생성

```bash
cd ../backend
python main.py --articles 3
```

### 5. 개발 서버 실행

```bash
cd ../frontend
npm run dev
```

브라우저에서 `http://localhost:3000` 열기

## 🔑 필요한 API 키

### Anthropic Claude API (필수)
1. [Anthropic Console](https://console.anthropic.com/) 방문
2. API Key 생성
3. `.env` 파일의 `ANTHROPIC_API_KEY`에 추가

### Google AdSense (필수)
1. [Google AdSense](https://www.google.com/adsense/) 계정 생성 및 승인
2. 광고 단위 생성
3. Client ID와 Slot ID를 `.env.local`에 추가

### Reddit API (선택사항)
1. [Reddit Apps](https://www.reddit.com/prefs/apps) 방문
2. Script 앱 생성
3. Client ID와 Secret을 `.env`에 추가

## 📦 프로젝트 구조

```
├── frontend/                    # Next.js 앱
│   ├── src/
│   │   ├── app/                # App Router 페이지
│   │   ├── components/         # React 컴포넌트
│   │   └── lib/                # 유틸리티 함수
│   ├── public/
│   │   └── articles/           # 생성된 아티클 JSON
│   └── package.json
├── backend/                     # Python 자동화
│   ├── scripts/
│   │   ├── fetch_trending.py  # 트렌드 수집
│   │   ├── generate_content.py # AI 콘텐츠 생성
│   │   ├── optimize_adsense.py # AdSense 최적화
│   │   └── save_article.py    # JSON 저장
│   ├── main.py                # 메인 실행 파일
│   └── config.yaml            # 설정
├── .env                        # 환경 변수
├── vercel.json                # Vercel 배포 설정
└── README.md
```

## 🌐 Vercel 배포

### 자동 배포 (GitHub 연동)

1. **GitHub에 푸시**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-github-repo>
git push -u origin main
```

2. **Vercel 연결**
- [Vercel](https://vercel.com) 접속
- "Import Project" 클릭
- GitHub 저장소 선택
- Root Directory를 `frontend`로 설정
- Environment Variables 추가:
  - `NEXT_PUBLIC_ADSENSE_CLIENT_ID`
  - `NEXT_PUBLIC_ADSENSE_SLOT_HEADER`
  - `NEXT_PUBLIC_ADSENSE_SLOT_IN_ARTICLE`
  - `NEXT_PUBLIC_ADSENSE_SLOT_FOOTER`
  - `NEXT_PUBLIC_SITE_NAME`
  - `NEXT_PUBLIC_SITE_URL`

3. **배포 완료!**
- Vercel이 자동으로 빌드 및 배포
- `your-project.vercel.app` URL 생성됨

### 수동 배포

```bash
cd frontend
npm install -g vercel
vercel
```

## 🌍 Cloudflare 도메인 연결

### 1. 도메인 구매
- [Cloudflare Domains](https://www.cloudflare.com/products/registrar/) 또는 다른 등록기관에서 도메인 구매

### 2. Cloudflare DNS 설정
1. Cloudflare 대시보드에서 도메인 추가
2. DNS 레코드 추가:
   - Type: `CNAME`
   - Name: `@` (또는 `www`)
   - Target: `cname.vercel-dns.com`
   - Proxy status: Proxied (주황색 구름)

### 3. Vercel에서 도메인 연결
1. Vercel 프로젝트 → Settings → Domains
2. 구매한 도메인 입력 (예: `yourdomain.com`)
3. DNS 레코드 확인 및 완료

### 4. SSL 자동 설정
- Cloudflare와 Vercel 모두 자동으로 SSL 인증서 발급

## 💰 수익 최적화

### AdSense 배치 전략
1. **헤더 광고**: 도입부 직후 (높은 가시성)
2. **본문 광고**: 콘텐츠 중간 (참여 시점)
3. **푸터 광고**: 아티클 끝 (이탈 방지)

### SEO 최적화
- 메타 태그 자동 생성
- Open Graph 이미지
- 구조화된 데이터
- 모바일 최적화
- 빠른 로딩 속도 (Next.js SSG)

### 콘텐츠 전략
- 트렌딩 토픽 타겟팅
- 1500-2000단어 (SEO 최적)
- 키워드 밀도 최적화
- 읽기 쉬운 구조

## 🔄 자동화 워크플로우

### GitHub Actions (선택사항)

`.github/workflows/generate-content.yml` 생성:

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
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
        run: |
          cd backend
          python main.py --articles 2
      - name: Commit and push
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add frontend/public/articles/
          git commit -m "Auto-generate articles" || exit 0
          git push
```

## 🎨 디자인 커스터마이징

### 색상 변경
`frontend/tailwind.config.ts`에서 색상 팔레트 수정:

```typescript
colors: {
  primary: {
    500: '#your-color',
    // ...
  },
}
```

### 레이아웃 수정
- `frontend/src/components/Header.tsx`
- `frontend/src/components/Footer.tsx`
- `frontend/src/app/layout.tsx`

## 📊 분석 추가

### Google Analytics

`frontend/src/app/layout.tsx`에 추가:

```tsx
<Script
  src={`https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX`}
  strategy="afterInteractive"
/>
<Script id="google-analytics" strategy="afterInteractive">
  {`
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-XXXXXXXXXX');
  `}
</Script>
```

## 🐛 문제 해결

### 콘텐츠가 표시되지 않음
```bash
# Backend에서 아티클 생성 확인
cd backend
python main.py --articles 1

# 생성된 파일 확인
ls -la ../frontend/public/articles/
```

### AdSense 광고가 표시되지 않음
1. `.env.local`에 AdSense Client ID 확인
2. AdSense 계정 승인 확인
3. 24-48시간 대기 (새 사이트)
4. 브라우저 광고 차단기 비활성화

### Vercel 빌드 실패
```bash
# 로컬에서 빌드 테스트
cd frontend
npm run build
```

## 📝 라이선스

MIT License - 상업적 사용 가능

## ⚠️ 주의사항

- Google AdSense 정책 준수 필수
- 생성된 콘텐츠는 검토 권장
- API 사용량 모니터링
- 백업 정기적으로 실행

## 🤝 기여

이슈와 PR 환영합니다!

---

**Happy Blogging! 💰📝**

Powered by Next.js, Claude AI, and Google AdSense
