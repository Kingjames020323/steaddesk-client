#!/usr/bin/env bash
set -euo pipefail
apk=${1:?expected merchant APK}
build_tools=$(find "${ANDROID_HOME:?}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
mkdir -p s6-device
keytool -genkeypair -alias lab -keyalg RSA -keysize 3072 -validity 30 -noprompt \
    -keystore "$RUNNER_TEMP/s6.p12" -storetype PKCS12 -storepass android -dname 'CN=S6 merchant lab'
"$build_tools/apksigner" sign --ks "$RUNNER_TEMP/s6.p12" --ks-pass pass:android --v4-signing-enabled false \
    --out s6-device/S6-merchant.apk "$apk"
(cd s6-device && "$build_tools/apksigner" verify --verbose --print-certs S6-merchant.apk > SIGNER.txt \
    && sha256sum S6-merchant.apk > SHA256SUMS)
