# AI 이슈 따라잡기 — 새 탭 AI 뉴스 크롬 확장

새 탭을 열면 최신 AI·테크·비즈니스 한국어 뉴스를 썸네일 카드와 한 줄 요약으로 보여준다.

## 구조

```
GitHub Actions (3시간마다)
  pipeline/build_feed.py
    한국어 RSS 14개 수집 → 영문 제외·종합매체는 AI 키워드 기사만 → 중복 제거 → 썸네일(og:image) 확보
    → 규칙 기반 처리 (API 키 불필요) → docs/feed.json 커밋
       · 한 줄 요약 = RSS 본문 첫 문장(기자명·머리말 제거)
       · 카테고리(AI/Vibe Coding/Business/etc) = 키워드 규칙 → 소스 기본값
       · 화제도(buzz) = 48시간 안에 같은 이슈를 다룬 다른 매체 수 → '인기 콘텐츠' 순위 (조회수 아님)
        │
        ▼  GitHub Pages (정적 JSON, CORS *)
extension/ (MV3, 새 탭 대체) ── ./sync-web.sh ──▶ docs/index.html (같은 화면의 반응형 웹)
  feed.json 하나만 fetch → chrome.storage에 캐시(30분) → 카드 렌더
  저장함·읽음 표시는 사용자 브라우저에만 저장 (서버로 보내는 데이터 없음)
```

서버도 API 키도 없다. public repo면 GitHub Pages·Actions 모두 무료라 운영비 0원.
Claude 요약이 필요해지면 `build_feed.py --ai`(+ `anthropic`·`pydantic` 설치, `ANTHROPIC_API_KEY`)로 켤 수 있다.

## 로컬 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/build_feed.py && ./sync-web.sh
.venv/bin/python -m http.server 8765 -d docs                      # → http://localhost:8765/ (웹 버전)
```

크롬에서 보기: `chrome://extensions` → 개발자 모드 → "압축해제된 확장 프로그램 로드" → `extension/` 선택.
(확장으로 열면 `config.js`의 `FEED_URL`을, 웹으로 열면 같은 폴더의 `feed.json`을 읽는다.)

## 배포 순서

1. GitHub에 public repo 생성 후 push
2. Settings → Pages → Branch `main` / 폴더 `/docs`
3. Actions → build-feed → Run workflow (첫 피드 생성)
4. `extension/config.js`의 `FEED_URL`을 `https://<user>.github.io/<repo>/feed.json`으로 수정
5. `./package.sh` → `dist/ai-issue-catchup-<version>.zip`
6. [Chrome 웹 스토어 개발자 대시보드](https://chrome.google.com/webstore/devconsole) 등록(1회 $5) → zip 업로드
   - 개인정보처리방침 URL: `https://<user>.github.io/<repo>/privacy.html`
   - 권한 사유: `storage` = 피드 캐시·저장한 기사 보관
   - 단일 목적: "새 탭에서 AI 뉴스 요약 제공"

## 소스 추가

`pipeline/sources.py`에 한 줄 추가. 한국어 콘텐츠만 남기므로(한글 비율 30% 미만 제외) 영문 소스는 넣어도 걸러진다. EO Planet은 RSS가 없어 제외했다.

## 주의

- 요약은 RSS 본문 첫 문장을 그대로 쓴다(재가공 없음). 기사 페이지는 썸네일·발행 시각 meta를 읽을 때만 새 기사당 1회 요청하고, 원문 링크를 항상 노출한다.
- 확장 이름에 다른 서비스의 이름·상표(예: "배달의~")를 쓰지 않는다. 스토어 심사에서 반려 사유가 된다.
