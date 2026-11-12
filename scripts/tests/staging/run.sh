#!/usr/bin/env bash
# Run with JDK 17 on PATH and a dedicated, rootable API 34 AOSP emulator.
# Optionally supply the unsigned merchant APK; Python 3.11+ and PyNaCl are then required.
# ANDROID_HOME=/path/to/sdk ANDROID_SERIAL=emulator-5554 bash scripts/tests/staging/run.sh
set -euo pipefail
[[ $# -le 1 ]] || { echo "Usage: run.sh [unsigned-merchant.apk]" >&2; exit 1; }
: "${ANDROID_HOME:?Set ANDROID_HOME to an SDK with platform 34 and build-tools 34.0.0}"
: "${ANDROID_SERIAL:?Set ANDROID_SERIAL to the test emulator}"
case "$ANDROID_SERIAL" in emulator-*) ;; *) echo "A dedicated emulator is required" >&2; exit 1 ;; esac
export PATH="$ANDROID_HOME/platform-tools:$PATH"
[[ $(adb shell getprop ro.kernel.qemu | tr -d '\r') == 1 ]]
[[ $(adb shell getprop ro.build.version.sdk | tr -d '\r') == 34 ]]
fixture=$(cd "$(dirname "$0")" && pwd)
production="$fixture/../../../android-staging/src/main/java/com/steaddesk/remote/staging"
build_tools="$ANDROID_HOME/build-tools/34.0.0"
android="$ANDROID_HOME/platforms/android-34/android.jar"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/classes" "$scratch/dex"
"$build_tools/aapt2" link -I "$android" --manifest "$fixture/AndroidManifest.xml" -o "$scratch/pkg.apk"
javac --release 8 -classpath "$android" -d "$scratch/classes" "$production"/*.java "$fixture"/*.java
jar cf "$scratch/classes.jar" -C "$scratch/classes" .
"$build_tools/d8" --lib "$android" --min-api 26 --output "$scratch/dex" "$scratch/classes.jar"
(cd "$scratch/dex" && zip -q "$scratch/pkg.apk" classes.dex)
"$build_tools/zipalign" -f 4 "$scratch/pkg.apk" "$scratch/aligned.apk"
# Ephemeral, throwaway certificate for the fixture APK.
keytool -genkeypair -keystore "$scratch/test.p12" -storepass android -keypass android \
    -alias test -dname CN=StagingTests -keyalg RSA -validity 1 -noprompt
"$build_tools/apksigner" sign --ks "$scratch/test.p12" --ks-pass pass:android \
    --out "$scratch/test.apk" "$scratch/aligned.apk"
python_bin=${STAGING_PYTHON:-python3}
"$python_bin" "$fixture/check_provider.py" "$scratch/test.apk"
if [[ $# == 1 ]]; then
    "$ANDROID_HOME/cmdline-tools/latest/bin/apkanalyzer" manifest print "$1" > "$scratch/manifest.xml"
    "$build_tools/apksigner" sign --ks "$scratch/test.p12" --ks-pass pass:android \
        --out "$scratch/merchant.apk" "$1"
    "$python_bin" "$fixture/merchant_smoke.py" "$scratch/merchant.apk" "$scratch/manifest.xml"
fi
