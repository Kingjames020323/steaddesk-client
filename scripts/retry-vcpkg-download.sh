#!/usr/bin/env bash
# Run the unchanged installer. Classify only its current attempt, before the
# workflow prints auxiliary buildtree logs which may describe older failures.
set -euo pipefail
log=$(mktemp)
trap 'rm -- "$log"' EXIT
for attempt in 1 2 3; do
  if "$@" 2>&1 | tee "$log"; then
    exit 0
  else
    status=("${PIPESTATUS[@]}")
  fi
  if (( status[1] != 0 )); then exit "${status[1]}"; fi
  if (( attempt == 3 )) ||
     ! grep -Eq 'error: curl operation failed with response code (408|429|500|502|503|504)\.' "$log" ||
     ! grep -Eq 'CMake Error at .*vcpkg_download_distfile\.cmake:' "$log" ||
     ! grep -Fq 'Download failed, halting portfile' "$log" ||
     grep -Eiq '(hash|checksum|digest).*(mismatch|does not match)|hash of the file .*does not match' "$log"; then
    exit "${status[0]}"
  fi
  delay=$((attempt * 30))
  echo "Transient vcpkg asset download failure. Retrying in $delay seconds." >&2
  sleep "$delay"
done
