#!/usr/bin/env bash
set -euo pipefail
queue=$(cd "$(dirname "$0")/.." && pwd)
source_tree=${1:-"$queue/upstream"}
cd "$source_tree"
test "$(git rev-parse HEAD)" = fada664df7a294d1d1a9ca3e7cd3637069122f17
test "$(git -C libs/hbb_common rev-parse HEAD)" = 229b904508364c8997aad0fb5af57effac859f60
for patch in "$queue"/patches/*.patch; do
  if git apply --reverse --check "$patch" 2>/dev/null; then continue; fi
  git apply --check "$patch"
  git apply "$patch"
done
for icon in res/icon.ico res/tray-icon.ico flutter/windows/runner/resources/app_icon.ico; do
  install -m 644 "$queue/branding/steaddesk.ico" "$icon"
done
install -m 644 "$queue/branding/png/256.png" flutter/assets/icon.png
for spec in mdpi:48:108 hdpi:72:162 xhdpi:96:216 xxhdpi:144:324 xxxhdpi:192:432; do
  IFS=: read -r density size adaptive <<< "$spec"
  dest="flutter/android/app/src/main/res/mipmap-$density"
  for name in ic_launcher ic_launcher_round; do install -m 644 "$queue/branding/png/$size.png" "$dest/$name.png"; done
  install -m 644 "$queue/branding/png/$adaptive.png" "$dest/ic_launcher_foreground.png"
done
