#!/usr/bin/env bash
# Run in the prepared RustDesk tree, after the ordinary unsigned merchant build.
set -euo pipefail
umask 077
queue=$(cd "$(dirname "$0")/.." && pwd)
tools=$(find "${ANDROID_HOME:?}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
scratch=$(mktemp -d "${RUNNER_TEMP:?}/s1-sign.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
out="$PWD/s1-pair"
mkdir "$out"
version=$(<RELEASE_VERSION)
[[ $version =~ ^1\.5\.0-sd\.([1-9][0-9]*)$ ]]
revision=${BASH_REMATCH[1]}

S1_PASSWORD=$(openssl rand -hex 32)
export S1_PASSWORD
keytool -genkeypair -keystore "$scratch/s1.p12" -storetype PKCS12 \
    -alias spike -keyalg RSA -keysize 3072 -validity 30 -dname 'CN=Temporary S1 Probe' \
    -storepass:env S1_PASSWORD -keypass:env S1_PASSWORD

for label in N N-plus-1; do
    if [[ $label == N-plus-1 ]]; then
        revision=$((revision + 1))
        version="1.5.0-sd.$revision"
        printf '%s\n' "$version" > RELEASE_VERSION
        bash "$queue/scripts/configure-edition.sh" "$PWD" merchant
        (cd flutter && flutter build apk --release --target-platform android-arm64,android-arm,android-x64)
    fi
    grep -Fx "const merchantVersion = \"$version\";" flutter/lib/steaddesk/merchant_build.dart
    apk="$out/SteadDesk-S1-$label.apk"
    "$tools/apksigner" sign --ks "$scratch/s1.p12" --ks-key-alias spike --ks-pass env:S1_PASSWORD \
        --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
        --out "$apk" flutter/build/app/outputs/flutter-apk/app-release.apk
    "$tools/apksigner" verify --verbose --print-certs "$apk" > "$scratch/certs"
    sed -nE 's/^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})$/\1/p' "$scratch/certs" > "$scratch/$label.sha"
    test "$(wc -l < "$scratch/$label.sha")" -eq 1
    "$tools/aapt" dump badging "$apk" > "$scratch/badging"
    grep -F "package: name='com.steaddesk.remote' versionCode='$((68 + revision))' versionName='$version'" "$scratch/badging"
    grep -Fx "targetSdkVersion:'36'" "$scratch/badging"
    "$tools/aapt" dump xmltree "$apk" AndroidManifest.xml > "$scratch/manifest"
    for entry in REQUEST_INSTALL_PACKAGES UPDATE_PACKAGES_WITHOUT_USER_ACTION; do
        grep -Fq "\"android.permission.$entry\"" "$scratch/manifest"
    done
    for entry in com.steaddesk.remote.spike android.intent.action.MY_PACKAGE_REPLACED; do
        grep -Fq "\"$entry\"" "$scratch/manifest"
    done
done
cmp "$scratch/N.sha" "$scratch/N-plus-1.sha"
cp "$scratch/N.sha" "$out/SIGNER-SHA256.txt"
(cd "$out" && sha256sum -- *.apk > SHA256SUMS && sha256sum --strict -c SHA256SUMS)
