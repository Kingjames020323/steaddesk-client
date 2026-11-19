#!/usr/bin/env bash
# The Flutter 3.24.5 included build resolves these AGP 7.3 dependencies before
# the application project is configured. Preserve the original Maven metadata.
set -euo pipefail
settings=${1:?Expected Flutter SDK Gradle settings.gradle.kts}
repo=${2:?Expected local Maven repository path}
sums=$(cd "$(dirname "$0")" && pwd)/flutter-gradle-bootstrap.sha256
mkdir -p "$repo"
while read -r digest path; do
  target="$repo/$path"
  mkdir -p "$(dirname "$target")"
  fetched=false
  for origin in https://repo.maven.apache.org/maven2 https://maven-central.storage-download.googleapis.com/maven2; do
    if curl --proto '=https' --proto-redir '=https' --fail --silent --show-error --location --retry 2 \
        --connect-timeout 8 --max-time 35 "$origin/$path" -o "$target.tmp"; then
      printf '%s  %s\n' "$digest" "$target.tmp" | sha256sum -c -
      mv "$target.tmp" "$target"
      fetched=true
      break
    fi
  done
  "$fetched" || { echo "Missing verified build dependency: $path" >&2; exit 1; }
done < "$sums"
python3 - "$settings" "$repo" <<'PY'
from pathlib import Path
import sys

settings, repo = map(Path, sys.argv[1:])
before = settings.read_text()
marker = '        google()'
local = f'''        maven {{
            url = uri("{repo.resolve().as_uri()}")
            content {{
                includeVersion("com.squareup", "javawriter", "2.5.0")
                includeVersion("org.ow2.asm", "asm", "9.1")
                includeVersion("org.sonatype.oss", "oss-parent", "7")
                includeVersion("org.ow2", "ow2", "1.5")
            }}
        }}
'''
if local not in before:
    if before.count(marker) != 1:
        raise SystemExit("Unexpected Flutter Gradle repository configuration")
    settings.write_text(before.replace(marker, local + marker))
PY
