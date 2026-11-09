"""콘텐츠 아카이브 — 피드에 한 번이라도 실린 기사를 id 기준으로 계속 쌓는다.

feed.json은 72시간치로 덮어써지므로, 행동 로그(GA4 click의 content_id)를 기사 속성과
붙이려면 따로 남겨 둬야 한다.

- 위치: archive/YYYY-MM.jsonl (처음 본 달 기준, 한 줄에 기사 1건). docs/ 밖이라 Pages로 서빙하지 않는다.
- 필드: feed.json 기사 필드 전부 + first_seen_at, last_seen_at, buzz_max, excerpt_len, pipeline_version.
  - 기사 필드(제목·요약·분류 등)는 가장 최근에 본 값으로 갱신한다.
  - 본문 발췌는 저작권 때문에 저장하지 않고 길이만 남긴다(수집기가 2500자에서 자르므로 상한 2500).
- id는 정규화 URL의 sha1 앞 12자리라 재수집해도 같다.

사용:
    python pipeline/archive.py --backfill   # docs/feed.json git 이력 전체로 아카이브를 다시 만든다
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "archive"
FEED_PATH = "docs/feed.json"


def load() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for f in sorted(ARCHIVE_DIR.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def save(rows: dict[str, dict]) -> None:
    by_month: dict[str, list[dict]] = {}
    for r in rows.values():
        by_month.setdefault(r["first_seen_at"][:7], []).append(r)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    for month, items in by_month.items():
        items.sort(key=lambda r: (r["first_seen_at"], r["id"]))
        text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in items)
        path = ARCHIVE_DIR / f"{month}.jsonl"
        if not path.exists() or path.read_text() != text:  # 바뀐 달만 다시 쓴다
            path.write_text(text)


def merge(rows: dict[str, dict], items: list[dict], seen_at: str, pipeline_version: int,
          excerpt_len: dict[str, int] | None = None) -> int:
    """피드 한 번 분량을 반영한다(시간 순서대로 호출). 새로 추가된 건수를 돌려준다."""
    excerpt_len = excerpt_len or {}
    added = 0
    for it in items:
        cur = rows.get(it["id"]) or {}
        added += not cur
        rows[it["id"]] = {
            **{k: v for k, v in it.items() if not k.startswith("_")},
            "first_seen_at": cur.get("first_seen_at", seen_at),
            "last_seen_at": seen_at,
            "buzz_max": max(cur.get("buzz_max") or 0, it.get("buzz") or 0),
            "excerpt_len": excerpt_len.get(it["id"], cur.get("excerpt_len")),
            "pipeline_version": pipeline_version,
        }
    return added


def update(items: list[dict], seen_at: str, pipeline_version: int, excerpt_len: dict[str, int]) -> None:
    """build_feed.py가 피드를 쓴 뒤 호출한다."""
    rows = load()
    added = merge(rows, items, seen_at, pipeline_version, excerpt_len)
    save(rows)
    print(f"→ archive/: 신규 {added}건, 누적 {len(rows)}건")


def backfill() -> None:
    """docs/feed.json의 git 이력을 오래된 것부터 읽어 아카이브를 처음부터 다시 만든다."""
    log = subprocess.run(["git", "log", "--reverse", "--format=%H", "--", FEED_PATH],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    snapshots = [(c, None) for c in log] + [(None, (ROOT / FEED_PATH).read_text())]
    rows: dict[str, dict] = {}
    for commit, text in snapshots:
        if text is None:
            text = subprocess.run(["git", "show", f"{commit}:{FEED_PATH}"],
                                  cwd=ROOT, capture_output=True, text=True, check=True).stdout
        feed = json.loads(text)
        merge(rows, feed["items"], feed["generated_at"], feed.get("version", 0))
    for f in ARCHIVE_DIR.glob("*.jsonl"):
        f.unlink()
    save(rows)
    print(f"백필: 스냅샷 {len(snapshots)}개 → 누적 {len(rows)}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="feed.json git 이력으로 아카이브 재생성")
    if parser.parse_args().backfill:
        backfill()
    else:
        parser.print_help()
