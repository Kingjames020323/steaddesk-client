#!/usr/bin/env bash
# Seed the two Maven Central dependencies of Flutter 3.24.5's included Gradle build.
set -euo pipefail
: "${RUNNER_TEMP:?}" "${FLUTTER_ROOT:?}"
manifest="$(dirname "$0")/android-gradle-deps.sha256"
repo="$RUNNER_TEMP/steaddesk-ci-maven"
mkdir -p "$repo"
fetch_verified() {
  local digest=$1 artifact=$2 source
  local target="$repo/$artifact"
  mkdir -p "$(dirname "$target")"
  for source in https://repo.maven.apache.org/maven2 https://maven-central.storage-download.googleapis.com/maven2; do
    if curl --fail --silent --show-error --location --proto '=https' --retry 2 \
        --connect-timeout 8 --max-time 30 "$source/$artifact" -o "$target.part" &&
        printf '%s  %s\n' "$digest" "$target.part" | shasum -a 256 -c; then
      mv "$target.part" "$target"
      return 0
    fi
  done
  echo "Could not obtain verified Maven dependency: $artifact" >&2
  return 1
}
while read -r digest artifact; do
  fetch_verified "$digest" "$artifact"
done < "$manifest"

init="${GRADLE_USER_HOME:-$HOME/.gradle}/init.d"
mkdir -p "$init"
cat > "$init/steaddesk-flutter-maven.gradle" <<'GRADLE'
beforeSettings { settings ->
    def plugin = new File(System.getenv('FLUTTER_ROOT'), 'packages/flutter_tools/gradle')
    if (settings.settingsDir.canonicalFile == plugin.canonicalFile) {
        settings.dependencyResolutionManagement.repositories.maven {
            url = new File(System.getenv('RUNNER_TEMP'), 'steaddesk-ci-maven').toURI()
        }
    }
}
GRADLE
