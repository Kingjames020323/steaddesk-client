#!/usr/bin/env bash
set -euo pipefail
queue=$(cd "$(dirname "$0")/.." && pwd)
source_tree=${1:-"$queue/upstream"}
cd "$source_tree"
test "$(git rev-parse HEAD)" = fada664df7a294d1d1a9ca3e7cd3637069122f17
test "$(git -C libs/hbb_common rev-parse HEAD)" = 229b904508364c8997aad0fb5af57effac859f60
# Later patches may edit lines introduced by earlier ones. Rewind the applied
# prefix in a disposable index, then preflight the entire queue before writing.
patches=("$queue"/patches/*.patch)
scratch=$(mktemp -d)
trap 'rm -r -- "$scratch"' EXIT
git init -q "$scratch"
while IFS= read -r -d '' record; do
  path=${record#*$'\t'}
  path=${path#*$'\t'}
  [[ -f $path ]] || continue
  mode=100644
  if [[ -x $path ]]; then mode=100755; fi
  blob=$(git -C "$scratch" hash-object -w --stdin < "$path")
  git -C "$scratch" update-index --add --cacheinfo "$mode,$blob,$path"
done < <(git apply --numstat -z "${patches[@]}")
applied=0
for ((i=${#patches[@]}-1; i>=0; i--)); do
  if git -C "$scratch" apply --cached --reverse "${patches[i]}" 2>/dev/null; then
    if ((applied == 0)); then applied=$((i+1)); fi
  elif ((applied != 0)); then
    echo "Inconsistent patch queue at ${patches[i]##*/}" >&2
    exit 1
  fi
done
for patch in "${patches[@]}"; do git -C "$scratch" apply --cached "$patch"; done
for ((i=applied; i<${#patches[@]}; i++)); do git apply "${patches[i]}"; done
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
