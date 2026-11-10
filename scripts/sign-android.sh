#!/usr/bin/env bash
# Usage: sign-android.sh RELEASE_DIR NEW_OUTPUT_DIR KEYSTORE KEY_ALIAS
set -euo pipefail
umask 077

if [[ $# -ne 4 || -z $4 ]]; then
  echo "Usage: $0 RELEASE_DIR NEW_OUTPUT_DIR KEYSTORE KEY_ALIAS" >&2
  exit 2
fi
release=$1
output=$2
keystore=$3
alias_name=$4
if [[ ! -f $keystore || -e $output || -L $output ]]; then
  echo "Provide an existing keystore and a new output directory." >&2
  exit 1
fi
command -v apksigner >/dev/null || { echo "Add Android SDK Build Tools apksigner to PATH." >&2; exit 1; }
helper="$(cd "$(dirname "$0")" && pwd)/signing_bundle.py"
scratch=$(mktemp -d "$(dirname "$output")/.steaddesk-sign-XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
trap 'exit 1' HUP INT TERM
unsigned=$(python3 "$helper" prepare android "$release" "$scratch")
signed="$scratch/${unsigned%.unsigned.apk}.apk"

# apksigner reads the password(s) at the terminal using its own console prompt.
apksigner sign --ks "$keystore" --ks-key-alias "$alias_name" \
  --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
  --out "$signed" "$scratch/bundle/$unsigned"
apksigner verify --verbose --print-certs "$signed" | tee "$scratch/verification.txt"
for scheme in 2 3; do
  if ! grep -Eq "^Verified using v${scheme} scheme .*: true[[:space:]]*$" "$scratch/verification.txt"; then
    echo "Verifier did not report APK Signature Scheme v$scheme as verified." >&2
    exit 1
  fi
done
python3 "$helper" publish android "$scratch" "$output"
printf 'Android signature verified. Release bundle written to %s\n' "$output"
