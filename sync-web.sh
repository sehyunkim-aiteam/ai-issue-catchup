#!/usr/bin/env bash
# 확장의 새 탭 화면을 GitHub Pages용 반응형 웹(docs/)으로 복사한다. feed.json·privacy.html은 건드리지 않는다.
set -euo pipefail
cd "$(dirname "$0")"
cp extension/newtab.html docs/index.html
cp extension/newtab.css extension/newtab.js extension/config.js docs/
mkdir -p docs/icons docs/fonts && cp extension/icons/* docs/icons/ && cp extension/fonts/* docs/fonts/
echo "→ docs/index.html 갱신"
