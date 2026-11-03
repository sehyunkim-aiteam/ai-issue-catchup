#!/usr/bin/env bash
# 웹스토어 업로드용 zip 생성. FEED_URL 미설정이면 중단.
set -euo pipefail
cd "$(dirname "$0")"
if grep -q YOUR_GITHUB_USER extension/config.js; then
  echo "✗ extension/config.js의 FEED_URL을 먼저 실제 주소로 바꾸세요." >&2; exit 1
fi
ver=$(python3 -c "import json;print(json.load(open('extension/manifest.json'))['version'])")
mkdir -p dist && rm -f "dist/ai-issue-catchup-$ver.zip"
(cd extension && zip -qr "../dist/ai-issue-catchup-$ver.zip" . -x '.*')
echo "→ dist/ai-issue-catchup-$ver.zip"
