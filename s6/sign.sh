#!/usr/bin/env bash
set -euo pipefail
apk=${1:?expected merchant APK}
build_tools=$(find "${ANDROID_HOME:?}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
"$build_tools/aapt" dump permissions "$apk" | grep -Fx "uses-permission: name='android.permission.SYSTEM_ALERT_WINDOW'" || {
    echo "S6b merchant APK must request SYSTEM_ALERT_WINDOW" >&2
    exit 1
}
scratch=$(mktemp -d "${RUNNER_TEMP:?}/s6-sign.XXXXXXXX")
trap 'rm -r -- "$scratch"' EXIT
S6_KEY_PASS=$(openssl rand -hex 32)
export S6_KEY_PASS
mkdir -p s6-device
keytool -genkeypair -alias lab -keyalg RSA -keysize 3072 -validity 30 -noprompt \
    -keystore "$scratch/lab.p12" -storetype PKCS12 -storepass:env S6_KEY_PASS -dname 'CN=S6 merchant lab'
"$build_tools/apksigner" sign --ks "$scratch/lab.p12" --ks-pass env:S6_KEY_PASS --v4-signing-enabled false \
    --out s6-device/S6-merchant.apk "$apk"
(cd s6-device && "$build_tools/apksigner" verify --verbose --print-certs S6-merchant.apk > SIGNER.txt \
    && sha256sum S6-merchant.apk > SHA256SUMS)
