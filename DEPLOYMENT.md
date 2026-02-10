# NexusTopic.com 배포 가이드

## 🚀 Vercel + Cloudflare 배포 완벽 가이드

도메인: **nexustopic.com** (Cloudflare 구매 완료 ✅)

---

## 📋 1단계: GitHub 저장소 준비

### Git 초기화 및 푸시

```bash
# 현재 디렉토리에서
git init
git add .
git commit -m "Initial commit: NexusTopic blog platform"

# GitHub에서 새 저장소 생성 후
git remote add origin https://github.com/YOUR_USERNAME/nexustopic-blog.git
git branch -M main
git push -u origin main
```

---

## 🌐 2단계: Vercel 배포

### 1. Vercel 계정 생성 및 프로젝트 연결

1. [Vercel](https://vercel.com) 접속
2. "New Project" 클릭
3. GitHub 저장소 선택 (nexustopic-blog)
4. **중요**: "Root Directory"를 `frontend`로 설정
5. Framework Preset: **Next.js** (자동 감지됨)

### 2. Environment Variables 설정

Vercel 대시보드에서 다음 환경변수 추가:

```env
# Google AdSense (나중에 승인 받은 후 추가)
NEXT_PUBLIC_ADSENSE_CLIENT_ID=ca-pub-XXXXXXXXXXXXXXXX
NEXT_PUBLIC_ADSENSE_SLOT_HEADER=1234567890
NEXT_PUBLIC_ADSENSE_SLOT_IN_ARTICLE=0987654321
NEXT_PUBLIC_ADSENSE_SLOT_FOOTER=1122334455

# Site Configuration
NEXT_PUBLIC_SITE_NAME=NexusTopic
NEXT_PUBLIC_SITE_URL=https://nexustopic.com
NEXT_PUBLIC_SITE_DESCRIPTION=Discover trending topics and insights powered by AI
```

### 3. 배포

- "Deploy" 클릭
- Vercel이 자동으로 빌드 및 배포
- 임시 URL 생성: `nexustopic.vercel.app`

---

## ☁️ 3단계: Cloudflare DNS 설정

### 1. Cloudflare 대시보드 접속

1. [Cloudflare Dashboard](https://dash.cloudflare.com/) 로그인
2. `nexustopic.com` 도메인 클릭

### 2. DNS 레코드 추가

**A. 루트 도메인 (nexustopic.com)**

```
Type: CNAME
Name: @
Target: cname.vercel-dns.com
Proxy status: DNS only (회색 구름) ⚠️ 처음에는 DNS only로!
TTL: Auto
```

**B. www 서브도메인 (www.nexustopic.com)**

```
Type: CNAME
Name: www
Target: cname.vercel-dns.com
Proxy status: DNS only (회색 구름)
TTL: Auto
```

### 3. 저장

- "Save" 클릭
- DNS 전파 대기 (5-10분)

---

## 🔗 4단계: Vercel에서 도메인 연결

### 1. Vercel 프로젝트 설정

1. Vercel 대시보드 → 프로젝트 선택
2. **Settings** → **Domains** 클릭

### 2. 커스텀 도메인 추가

```
nexustopic.com
```

입력 후 "Add" 클릭

### 3. www 도메인도 추가 (선택사항)

```
www.nexustopic.com
```

### 4. DNS 검증

- Vercel이 자동으로 DNS 레코드 확인
- ✅ 초록색 체크마크가 뜨면 성공!
- ⚠️ 빨간색 에러가 뜨면 DNS 레코드 다시 확인

---

## 🔒 5단계: SSL 인증서 (자동)

### Vercel SSL
- Vercel이 자동으로 Let's Encrypt SSL 인증서 발급
- 5-10분 소요
- 완료되면 `https://nexustopic.com` 접속 가능

### Cloudflare Proxy 활성화 (선택사항)

SSL 인증서 발급 완료 후:
1. Cloudflare DNS 설정으로 돌아가기
2. CNAME 레코드의 Proxy status를 "Proxied" (주황색 구름)로 변경
3. 추가 보안 + CDN 가속 활성화

---

## 📝 6단계: 콘텐츠 생성 및 배포

### 1. 로컬에서 아티클 생성

```bash
cd backend

# .env 파일 생성
cp ../.env.example .env
# ANTHROPIC_API_KEY 등 설정

# 아티클 생성
python main.py --articles 3
```

### 2. Git으로 푸시

```bash
# 루트 디렉토리에서
git add frontend/public/articles/
git commit -m "Add initial articles"
git push
```

### 3. 자동 배포

- Vercel이 자동으로 감지하고 재배포
- 2-3분 후 `https://nexustopic.com`에서 확인 가능

---

## 🎨 7단계: Google AdSense 신청

### 1. 사이트에 콘텐츠 추가

- 최소 10-15개 고품질 아티클 생성
- 다양한 카테고리 (기술, 비즈니스, 뉴스 등)

```bash
cd backend
python main.py --articles 15
git add frontend/public/articles/
git commit -m "Add more articles for AdSense"
git push
```

### 2. Google AdSense 신청

1. [Google AdSense](https://www.google.com/adsense/) 접속
2. "시작하기" 클릭
3. 웹사이트 URL 입력: `https://nexustopic.com`
4. 이메일 주소 입력
5. AdSense 코드를 사이트에 추가 (이미 설정되어 있음)

### 3. 승인 대기

- 보통 1-2주 소요
- 승인 기준:
  - ✅ 독창적이고 유용한 콘텐츠
  - ✅ 사용하기 쉬운 사이트
  - ✅ 충분한 콘텐츠 (10개 이상 아티클)
  - ✅ 정책 준수 (저작권, 성인물 금지 등)

### 4. 승인 후 환경변수 업데이트

Vercel 대시보드에서:
```env
NEXT_PUBLIC_ADSENSE_CLIENT_ID=ca-pub-1234567890123456
NEXT_PUBLIC_ADSENSE_SLOT_HEADER=1111111111
NEXT_PUBLIC_ADSENSE_SLOT_IN_ARTICLE=2222222222
NEXT_PUBLIC_ADSENSE_SLOT_FOOTER=3333333333
```

---

## 🔄 8단계: 자동화 설정 (선택사항)

### GitHub Actions로 자동 콘텐츠 생성

`.github/workflows/generate-content.yml` 생성:

```yaml
name: Generate Content Daily

on:
  schedule:
    - cron: '0 10 * * *'  # 매일 오전 10시 (UTC)
  workflow_dispatch:  # 수동 실행 가능

jobs:
  generate-articles:
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
          git commit -m "🤖 Auto-generate daily articles" || exit 0
          git push
```

### GitHub Secrets 설정

1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. 다음 secrets 추가:
   - `ANTHROPIC_API_KEY`
   - `REDDIT_CLIENT_ID` (선택)
   - `REDDIT_CLIENT_SECRET` (선택)

---

## ✅ 배포 체크리스트

### 배포 전
- [ ] Git 저장소 생성 및 푸시
- [ ] `.env` 파일 설정 (로컬)
- [ ] Backend에서 테스트 아티클 생성

### Vercel 설정
- [ ] Vercel 프로젝트 생성
- [ ] Root Directory를 `frontend`로 설정
- [ ] Environment Variables 추가
- [ ] 첫 배포 성공 확인

### DNS 설정
- [ ] Cloudflare DNS 레코드 추가 (CNAME)
- [ ] Vercel에서 도메인 연결
- [ ] SSL 인증서 발급 확인
- [ ] `https://nexustopic.com` 접속 테스트

### 콘텐츠
- [ ] 10-15개 아티클 생성
- [ ] Git 푸시 및 자동 배포 확인
- [ ] 사이트에서 아티클 표시 확인

### AdSense
- [ ] Google AdSense 신청
- [ ] 승인 대기
- [ ] 승인 후 광고 코드 업데이트

---

## 🐛 문제 해결

### DNS가 전파되지 않음
```bash
# DNS 확인
nslookup nexustopic.com
dig nexustopic.com

# 5-10분 대기 후 재확인
```

### Vercel 도메인 검증 실패
1. Cloudflare DNS에서 Proxy status를 "DNS only"로 변경
2. 5분 대기
3. Vercel에서 다시 검증
4. 성공 후 Proxy 활성화

### 아티클이 표시되지 않음
```bash
# 로컬에서 확인
cd backend
python main.py --articles 1
ls -la ../frontend/public/articles/

# Git 푸시 확인
git status
git add frontend/public/articles/
git commit -m "Add articles"
git push
```

### SSL 인증서 오류
- Vercel에서 자동 발급 (5-10분 소요)
- Cloudflare Proxy를 일시적으로 비활성화
- 브라우저 캐시 삭제

---

## 📊 모니터링

### 트래픽 확인
- **Vercel Analytics**: Vercel 대시보드에서 확인
- **Cloudflare Analytics**: Cloudflare 대시보드에서 확인
- **Google Analytics**: (선택) 추가 설정 가능

### AdSense 수익
- [AdSense Dashboard](https://www.google.com/adsense/)에서 확인
- 일일 수익, 클릭률, 페이지 조회수 등

---

## 🎉 완료!

축하합니다! **NexusTopic.com** 배포가 완료되었습니다!

**다음 단계:**
1. ✅ 콘텐츠 생성 (매일 2-3개)
2. ✅ AdSense 승인 받기
3. ✅ SEO 최적화
4. ✅ 트래픽 모니터링
5. ✅ 수익 확인

**문의사항이 있으면 언제든지 물어보세요!** 🚀
