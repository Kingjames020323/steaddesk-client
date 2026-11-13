#!/usr/bin/env bash
# Run in the prepared RustDesk tree, after the ordinary unsigned merchant build.
set -Eeuo pipefail
step=setup
label=setup
# Log the source command, never expanded arguments (the password is environment-only).
trap 'printf "S1 [%s/%s] line %s: expected success, exit %d: %s\n" "$label" "$step" "$LINENO" "$?" "$BASH_COMMAND" >&2' ERR
fail() { printf 'S1 [%s/%s] %s\n' "$label" "$step" "$*" >&2; exit 1; }
umask 077
queue=$(cd "$(dirname "$0")/.." && pwd)
tools=$(find "${ANDROID_HOME:?}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
scratch=$(mktemp -d "${RUNNER_TEMP:?}/s1-sign.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
out="$PWD/s1-pair"
mkdir "$out"
version=$(<RELEASE_VERSION)
[[ $version =~ ^1\.5\.0-sd\.([1-9][0-9]*)$ ]] || fail "expected 1.5.0-sd.N, read [$version]"
revision=${BASH_REMATCH[1]}

tool_version=$("$tools/apksigner" version)
printf 'S1 using %s (apksigner %s)\n' "$tools" "$tool_version"
step=generate-ephemeral-key
S1_PASSWORD=$(openssl rand -hex 32)
export S1_PASSWORD
keytool -genkeypair -keystore "$scratch/s1.p12" -storetype PKCS12 \
    -alias spike -keyalg RSA -keysize 3072 -validity 30 -dname 'CN=Temporary S1 Probe' \
    -storepass:env S1_PASSWORD -keypass:env S1_PASSWORD

for label in N N-plus-1; do
    if [[ $label == N-plus-1 ]]; then
        step=build-next-version
        revision=$((revision + 1))
        version="1.5.0-sd.$revision"
        printf '%s\n' "$version" > RELEASE_VERSION
        bash "$queue/scripts/configure-edition.sh" "$PWD" merchant
        (cd flutter && flutter build apk --release --target-platform android-arm64,android-arm,android-x64)
    fi
    step=check-merchant-version
    grep -Fx "const merchantVersion = \"$version\";" flutter/lib/steaddesk/merchant_build.dart ||
        fail "expected merchantVersion=$version, read [$(grep -F merchantVersion flutter/lib/steaddesk/merchant_build.dart || true)]"
    apk="$out/SteadDesk-S1-$label.apk"
    step=sign-apk
    "$tools/apksigner" sign --ks "$scratch/s1.p12" --ks-key-alias spike --ks-pass env:S1_PASSWORD \
        --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
        --out "$apk" flutter/build/app/outputs/flutter-apk/app-release.apk
    step=verify-apk
    "$tools/apksigner" verify --verbose --print-certs "$apk" | tee "$scratch/certs"
    step=read-signer
    python3 "$queue/scripts/s1_signer.py" < "$scratch/certs" > "$scratch/$label.sha"
    step=check-manifest
    "$tools/aapt" dump badging "$apk" > "$scratch/badging"
    expected="package: name='com.steaddesk.remote' versionCode='$((68 + revision))' versionName='$version'"
    grep -F "$expected" "$scratch/badging" ||
        fail "expected [$expected], read [$(grep '^package:' "$scratch/badging" || true)]"
    grep -Fx "targetSdkVersion:'36'" "$scratch/badging" ||
        fail "expected targetSdkVersion 36, read [$(grep '^targetSdkVersion:' "$scratch/badging" || true)]"
    "$tools/aapt" dump xmltree "$apk" AndroidManifest.xml > "$scratch/manifest"
    for entry in REQUEST_INSTALL_PACKAGES UPDATE_PACKAGES_WITHOUT_USER_ACTION; do
        grep -Fq "\"android.permission.$entry\"" "$scratch/manifest" ||
            fail "expected $entry in $apk manifest, found zero matches"
    done
    for entry in com.steaddesk.remote.spike android.intent.action.MY_PACKAGE_REPLACED; do
        grep -Fq "\"$entry\"" "$scratch/manifest" ||
            fail "expected $entry in $apk manifest, found zero matches"
    done
done
step=compare-signers
cmp -s "$scratch/N.sha" "$scratch/N-plus-1.sha" ||
    fail "expected $(cat "$scratch/N.sha"), read $(cat "$scratch/N-plus-1.sha")"
step=package-checksums
cp "$scratch/N.sha" "$out/SIGNER-SHA256.txt"
(cd "$out" && sha256sum -- *.apk > SHA256SUMS && sha256sum --strict -c SHA256SUMS)
