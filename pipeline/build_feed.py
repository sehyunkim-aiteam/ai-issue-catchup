"""RSS 수집 → 썸네일 확보 → 규칙 기반 요약·분류·화제도 → docs/feed.json.

API 키 없이 돈다. 모든 판정은 규칙이다.
- 한국어 콘텐츠만 남긴다(제목+발췌의 한글 비율).
- 요약: RSS 본문 첫 문장(기자명·괄호 머리말 등 잡음 제거).
- 분류: 제목·본문 키워드 규칙 → 안 걸리면 소스 기본값.
- 화제도(buzz): 최근 48시간 안에 '다른 매체'가 같은 이슈(제목 핵심어 2개 이상 겹침)를 다룬 수.
  인기 콘텐츠 순위에 쓴다. 조회수가 아니다.
- 이미 처리한 기사(URL 기준)는 이전 feed.json에서 썸네일·발행 시각을 재사용한다.

선택: --ai 를 주면 새 기사만 Claude Haiku 5.5로 한 줄 요약·분류를 덮어쓴다(ANTHROPIC_API_KEY 필요).

사용:
    python pipeline/build_feed.py
    python pipeline/build_feed.py --ai
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser

sys.path.insert(0, str(Path(__file__).parent))
from sources import SOURCES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "feed.json"
FEED_VERSION = 4
WINDOW_HOURS = 72
BUZZ_HOURS = 48
MAX_ITEMS = 300
MAX_EXCERPT_CHARS = 2500
MIN_HANGUL_RATIO = 0.3
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# ───────────────────────── 분류 규칙 ─────────────────────────
# 위에서부터 먼저 걸리는 분류를 쓴다. 영문 키워드는 대소문자 무시.

KW_VIBE = re.compile(
    r"바이브\s?코딩|코딩|개발자|프로그래밍|코드\s?리뷰|커서\b|cursor|claude\s?code|클로드\s?코드|코덱스|codex|"
    r"copilot|코파일럿|깃허브|github|오픈소스|프레임워크|sdk|\bapi\b|\bmcp\b|\bide\b|리팩터|프론트엔드|백엔드",
    re.I)
KW_AI = re.compile(
    r"\bai\b|a\.i\.|인공지능|생성형|llm|\bgpt|챗gpt|chatgpt|오픈ai|openai|앤트로픽|anthropic|클로드|claude|"
    r"제미나이|gemini|딥시크|deepseek|라마\b|llama|미스트랄|에이전트|agent|파운데이션\s?모델|언어\s?모델|추론\s?모델|"
    r"머신러닝|딥러닝|엔비디아|nvidia|gpu|hbm|ai\s?반도체|프롬프트|소버린|피지컬\s?ai|ax\b|코파일럿",
    re.I)
KW_BIZ = re.compile(r"투자|유치|시리즈\s?[a-d]|매출|실적|영업이익|인수|합병|m&a|상장|ipo|펀딩|기업가치|스타트업|빅테크", re.I)


def classify(text: str, default: str) -> str:
    if KW_VIBE.search(text):
        return "vibe_coding"
    if default == "business":          # 종합 매체는 AI 키워드 통과분만 들어온다
        return "business" if KW_BIZ.search(text) else "ai"
    if default == "ai":
        return "ai"
    return "ai" if KW_AI.search(text) else "etc"   # 개발 매체의 일반 기술 글


# ───────────────────────── 공통 ─────────────────────────

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|ref_src$)")
HANGUL = re.compile(r"[가-힣]")
LETTER = re.compile(r"[A-Za-z가-힣]")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def clean_text(raw: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def is_korean(text: str) -> bool:
    letters = LETTER.findall(text)
    return bool(letters) and len(HANGUL.findall(text)) / len(letters) >= MIN_HANGUL_RATIO


def entry_time(entry) -> float | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return calendar.timegm(t)
    return None


def http_get(url: str, limit: int = 400_000, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(limit)
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


# ───────────────────────── 한 줄 요약 ─────────────────────────

LEAD_NOISE = [
    re.compile(r"^\s*[\[【(〔][^\]】)〕]{0,40}[\]】)〕]\s*"),            # [AI타임스], (서울=연합뉴스) 등 머리말
    re.compile(r"^[가-힣]{2,4}\s?(기자|특파원|에디터)\s*[=·|]?\s*"),        # 홍길동 기자 =
    re.compile(r"^\S+@\S+\s*"),                                          # 이메일
    re.compile(r"^(사진|이미지|출처)\s*[=:]\s*\S+\s*"),
]
SENT_END = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)|(?<=요\.)")


def one_line(title: str, excerpt: str) -> str:
    text = excerpt
    for _ in range(3):
        for pat in LEAD_NOISE:
            text = pat.sub("", text)
    text = text.lstrip("▲△■□●◆-–— ").strip()
    if not text:
        return ""
    sentence = SENT_END.split(text, maxsplit=1)[0].strip()
    # 제목을 그대로 반복하는 첫 문장은 버리고 다음 문장을 쓴다
    if re.sub(r"\W", "", sentence)[:20] == re.sub(r"\W", "", title)[:20]:
        rest = text[len(sentence):].strip()
        sentence = SENT_END.split(rest, maxsplit=1)[0].strip() if rest else ""
    return sentence[:90]


# ───────────────────────── 화제도 ─────────────────────────

JOSA = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|까지|부터|이다|했다|한다|하는|하고|한|된|될)$")
STOP = {"기자", "뉴스", "오늘", "올해", "내년", "관련", "위해", "통해", "대한", "최대", "최초", "공개", "출시",
        "발표", "진행", "개최", "선정", "기업", "서비스", "시장", "국내", "글로벌", "the", "and", "for", "with"}


def keywords(title: str) -> set[str]:
    words = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9.+-]+|[가-힣0-9]+", title):
        w = JOSA.sub("", w.lower()) if HANGUL.search(w) else w.lower()
        if len(w) >= 2 and w not in STOP and not w.isdigit():
            words.add(w)
    return words


def add_buzz(items: list[dict]) -> None:
    """다른 매체가 같은 이슈를 다룬 수. 같은 매체끼리는 세지 않는다.

    'ai'·'스타트업'처럼 제목 여기저기 나오는 흔한 단어(전체 제목의 4% 초과 등장)는 빼고,
    남은 핵심어가 2개 이상 겹쳐야 같은 이슈로 본다.
    """
    keys = [keywords(it["title"]) for it in items]
    df: dict[str, int] = {}
    for k in keys:
        for w in k:
            df[w] = df.get(w, 0) + 1
    common = {w for w, n in df.items() if n > max(3, len(items) * 0.04)}
    keys = [k - common for k in keys]
    ts = [datetime.fromisoformat(it["published_at"]).timestamp() for it in items]
    for i, it in enumerate(items):
        others = set()
        for j, jt in enumerate(items):
            if i == j or jt["source_id"] == it["source_id"] or abs(ts[i] - ts[j]) > BUZZ_HOURS * 3600:
                continue
            if len(keys[i] & keys[j]) >= 2:
                others.add(jt["source_id"])
        it["buzz"] = len(others)


# ───────────────────────── 수집 ─────────────────────────

def feed_image(entry, raw_html: str) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', raw_html or "")
    return html.unescape(m.group(1)) if m else None


def fetch_source(src: dict, now: float, first_seen: dict[str, float]) -> list[dict]:
    try:
        feed = feedparser.parse(http_get(src["url"], limit=5_000_000, timeout=20))
    except Exception as exc:
        print(f"  ✗ {src['name']}: {exc}", file=sys.stderr)
        return []
    items, skipped_lang, skipped_topic = [], 0, 0
    for e in feed.entries:
        link, ts = e.get("link"), entry_time(e)
        guessed = False
        if link and not ts:  # 날짜 없는 피드(요즘IT 등): 이전 기록 → 기사 페이지 meta(enrich) → 최초 발견 시각
            ts = first_seen.get(normalize_url(link))
            guessed = ts is None
            ts = ts or now
        if not link or now - ts > WINDOW_HOURS * 3600 or ts > now + 3600:
            continue
        raw_body = (e["content"][0].get("value", "") if e.get("content") else "") or e.get("summary", "")
        title, body = clean_text(e.get("title", "")), clean_text(raw_body)
        if not is_korean(f"{title} {body[:500]}"):
            skipped_lang += 1
            continue
        if src.get("require_ai") and not (KW_AI.search(title) or KW_AI.search(body[:800])):
            skipped_topic += 1
            continue
        url = normalize_url(link)
        items.append({
            "id": hashlib.sha1(url.encode()).hexdigest()[:12],
            "url": url,
            "title": title,
            "source": src["name"],
            "source_id": src["id"],
            "published_at": datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds"),
            "image": feed_image(e, raw_body),
            "summary": one_line(title, body),
            "category": classify(f"{title} {body[:800]}", src["category"]),
            "_excerpt": body[:MAX_EXCERPT_CHARS],
            "_date_guessed": guessed,
        })
        if len(items) >= src["max_items"]:
            break
    notes = [f"영문 제외 {skipped_lang}"] * bool(skipped_lang) + [f"AI 무관 제외 {skipped_topic}"] * bool(skipped_topic)
    print(f"  ✓ {src['name']}: {len(items)}건" + (f" ({', '.join(notes)})" if notes else ""))
    return items


def dedupe(items: list[dict]) -> list[dict]:
    seen_url, seen_title, out = set(), set(), []
    for it in sorted(items, key=lambda x: x["published_at"]):
        title_key = re.sub(r"\W+", "", it["title"].lower())[:40]
        if it["url"] in seen_url or (title_key and title_key in seen_title):
            continue
        seen_url.add(it["url"])
        seen_title.add(title_key)
        out.append(it)
    return out


def meta_content(page: str, *names: str) -> str | None:
    for name in names:
        for pat in (rf'<meta[^>]+(?:property|name|itemprop)=["\']{name}["\'][^>]*content=["\']([^"\']+)',
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']{name}["\']'):
            m = re.search(pat, page, re.I)
            if m:
                return html.unescape(m.group(1)).strip()
    return None


def page_meta(url: str) -> tuple[str | None, float | None]:
    """기사 페이지에서 (og:image, 발행 시각)을 읽는다."""
    try:
        page = http_get(url)
    except Exception:
        return None, None
    img = meta_content(page, "og:image", "twitter:image", "twitter:image:src")
    if img:
        img = urljoin(url, "https:" + img if img.startswith("//") else img)
    ts = None
    raw = meta_content(page, "article:published_time", "datePublished", "pubdate")
    if not raw:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
        raw = m.group(1) if m else None
    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            ts = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
        except ValueError:
            pass
    return img, ts


def enrich(items: list[dict], now: float) -> list[dict]:
    """썸네일이 없거나 날짜를 추정한 기사만 페이지를 열어 보강한다. 보강 후 기간 밖이면 뺀다."""
    need = [it for it in items if not it.get("image") or it.get("_date_guessed")]
    with ThreadPoolExecutor(max_workers=10) as pool:
        for it, (img, ts) in zip(need, pool.map(lambda x: page_meta(x["url"]), need)):
            if not it.get("image"):
                it["image"] = img
            if it.get("_date_guessed") and ts:
                it["published_at"] = datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")
    for it in items:  # http 이미지는 확장 페이지에서 mixed content로 막히므로 https로 올린다
        if (it.get("image") or "").startswith("http://"):
            it["image"] = "https://" + it["image"][7:]
    cutoff = now - WINDOW_HOURS * 3600
    kept = [it for it in items if datetime.fromisoformat(it["published_at"]).timestamp() >= cutoff]
    got = sum(1 for it in kept if it.get("image"))
    print(f"썸네일 {got}/{len(kept)}건 확보" + (f", 기간 밖 {len(items) - len(kept)}건 제외" if len(kept) < len(items) else ""))
    return kept


# ───────────────────────── 선택: Claude 요약 ─────────────────────────

def ai_overwrite(items: list[dict], workers: int = 8) -> None:
    """--ai 일 때만: 새 기사의 summary·category를 Claude 판정으로 덮어쓴다. 실패한 기사는 규칙 값 유지."""
    from typing import Literal

    import anthropic
    from pydantic import BaseModel, Field

    class ArticleSummary(BaseModel):
        summary: str = Field(description="기사 핵심을 담은 한국어 한 문장. 45자 이내, '~했다/~한다' 평서문")
        category: Literal["ai", "vibe_coding", "business", "etc"] = Field(description=(
            "ai=AI 모델·서비스·연구·정책 / vibe_coding=AI 코딩도구·개발 실무 / business=투자·실적·스타트업·빅테크 전략 / etc=그 외"))

    client = anthropic.Anthropic()

    def run(it: dict) -> None:
        try:
            resp = client.messages.parse(
                model="claude-haiku-5-5",
                max_tokens=2000,
                system="한국 IT 직장인을 위한 뉴스 큐레이터다. 제목과 RSS 발췌만 근거로 판단하고, 요약에 제목을 반복하지 않는다.",
                messages=[{"role": "user", "content": f"제목: {it['title']}\n본문 발췌:\n{it['_excerpt'] or '(없음)'}"}],
                output_format=ArticleSummary,
            )
            if resp.stop_reason != "refusal" and resp.parsed_output:
                it["summary"] = resp.parsed_output.summary.strip()
                it["category"] = resp.parsed_output.category
                it["ai"] = True
        except Exception as exc:
            print(f"  ! 요약 실패 {it['url']}: {exc}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, items))


# ───────────────────────── 메인 ─────────────────────────

CARRY = ("image", "published_at", "summary", "category", "ai")


def load_previous() -> tuple[dict[str, dict], dict[str, float]]:
    """(재사용할 처리 결과, URL별 최초 발견 시각)"""
    try:
        prev = json.loads(OUT.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}
    rows = prev.get("items", [])
    first_seen = {it["url"]: datetime.fromisoformat(it["published_at"]).timestamp()
                  for it in rows if it.get("published_at")}
    reuse = {it["url"]: it for it in rows} if prev.get("version") == FEED_VERSION else {}
    return reuse, first_seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="새 기사를 Claude로 요약·분류 (ANTHROPIC_API_KEY 필요)")
    args = parser.parse_args()

    now = time.time()
    prev, first_seen = load_previous()
    print("RSS 수집")
    with ThreadPoolExecutor(max_workers=8) as pool:
        raw = [it for batch in pool.map(lambda s: fetch_source(s, now, first_seen), SOURCES) for it in batch]
    items = dedupe(raw)

    todo = [it for it in items if it["url"] not in prev]
    print(f"기사 {len(items)}건 (재사용 {len(items) - len(todo)} / 신규 {len(todo)})")
    todo = enrich(todo, now)
    if args.ai and todo:
        ai_overwrite(todo)

    todo_by_url = {it["url"]: it for it in todo}
    out = []
    for it in items:
        if it["url"] in prev:
            p = prev[it["url"]]
            it.update({k: p[k] for k in CARRY if k in p})
        elif it["url"] not in todo_by_url:
            continue  # 보강 후 기간 밖으로 빠진 기사
        out.append({k: v for k, v in it.items() if not k.startswith("_")})

    add_buzz(out)
    out.sort(key=lambda x: x["published_at"], reverse=True)
    feed = {
        "version": FEED_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": out[:MAX_ITEMS],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    hot = sum(1 for it in feed["items"] if it["buzz"] > 0)
    print(f"→ {OUT.relative_to(ROOT)}: {len(feed['items'])}건 (다른 매체도 다룬 이슈 {hot}건)")


if __name__ == "__main__":
    main()
